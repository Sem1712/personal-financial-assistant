"""Validate and normalize supported local bank workbooks."""

import asyncio
import hashlib
import os
import re
import stat
import zlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from python_calamine import CalamineError, CalamineWorkbook

MAX_FILE_SIZE = 20 * 1024 * 1024
MAX_EXPANDED_SIZE = 200 * 1024 * 1024
MAX_ENTRIES = 500
MAX_RATIO = 100
HEADINGS = (
    "data",
    "operazione",
    "dettagli",
    "conto o carta",
    "contabilizzazione",
    "categoria",
    "valuta",
    "importo",
)
SHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"


class WorkbookError(Exception):
    """A workbook is unsupported or invalid; details contain no cell values."""


@dataclass(frozen=True)
class Observation:
    sheet_index: int
    row_number: int
    account_reference: str
    transaction_date: date
    amount_minor: int
    currency: str
    operation: str | None
    details: str | None
    booking_status: str
    category: str | None


@dataclass(frozen=True)
class FileSnapshot:
    path: Path
    signature: tuple[int, int, int, int, int]


@dataclass(frozen=True)
class ParsedFile:
    sha256: str
    observations: list[Observation]
    account_reference: str | None


def _signature(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _discover(directory: Path) -> list[FileSnapshot]:
    try:
        with os.scandir(directory) as entries:
            result: list[FileSnapshot] = []
            for entry in entries:
                if (
                    entry.name.startswith("~$")
                    or not entry.name.lower().endswith(".xlsx")
                    or not entry.is_file(follow_symlinks=False)
                ):
                    continue
                info = entry.stat(follow_symlinks=False)
                result.append(FileSnapshot(Path(entry.path), _signature(info)))
            return sorted(result, key=lambda item: item.path.name)
    except OSError:
        raise WorkbookError("unable to read input directory") from None


async def discover_workbooks(directory: Path) -> list[FileSnapshot]:
    """Snapshot eligible regular files directly under the selected directory."""
    return await asyncio.to_thread(_discover, directory)


def _read_file(snapshot: FileSnapshot) -> ParsedFile:
    try:
        descriptor = os.open(snapshot.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as source:
            before = os.fstat(source.fileno())
            if (
                not stat.S_ISREG(before.st_mode)
                or _signature(before) != snapshot.signature
                or before.st_size > MAX_FILE_SIZE
            ):
                raise WorkbookError("input file changed or exceeds size limit")
            data = source.read(MAX_FILE_SIZE + 1)
            if (
                len(data) > MAX_FILE_SIZE
                or _signature(os.fstat(source.fileno())) != snapshot.signature
            ):
                raise WorkbookError("input file changed or exceeds size limit")
        observations, account_reference = _parse_workbook(data)
        if (
            _signature(os.stat(snapshot.path, follow_symlinks=False))
            != snapshot.signature
        ):
            raise WorkbookError("input file changed")
        return ParsedFile(
            hashlib.sha256(data).hexdigest(), observations, account_reference
        )
    except OSError:
        raise WorkbookError("unable to read input file") from None


async def read_workbook(snapshot: FileSnapshot) -> ParsedFile:
    """Read, hash and parse the same stable bytes outside the event loop."""
    return await asyncio.to_thread(_read_file, snapshot)


def _check_snapshots(snapshots: Sequence[FileSnapshot]) -> None:
    for ordinal, snapshot in enumerate(snapshots, 1):
        try:
            info = os.stat(snapshot.path, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or _signature(info) != snapshot.signature:
                raise WorkbookError(f"file {ordinal}: input file changed")
        except OSError:
            raise WorkbookError(
                f"file {ordinal}: unable to verify input file"
            ) from None


async def check_snapshots(snapshots: Sequence[FileSnapshot]) -> None:
    """Recheck discovered files before committing their batch."""
    await asyncio.to_thread(_check_snapshots, snapshots)


def _validate_archive(
    data: bytes,
) -> tuple[dict[int, set[str]], dict[int, dict[str, str]]]:
    if len(data) > MAX_FILE_SIZE:
        raise WorkbookError("workbook exceeds size limit")
    try:
        with ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ENTRIES:
                raise WorkbookError("workbook has too many parts")
            names = [entry.filename for entry in entries]
            if len(set(names)) != len(names):
                raise WorkbookError("duplicate workbook parts")
            if sum(entry.file_size for entry in entries) > MAX_EXPANDED_SIZE:
                raise WorkbookError("expanded workbook exceeds size limit")
            for entry in entries:
                name = entry.filename.lower()
                if (
                    entry.flag_bits & 1
                    or entry.file_size > MAX_RATIO * max(entry.compress_size, 1)
                    or "vbaproject" in name
                    or name.startswith("xl/externallinks/")
                    or ".." in PurePosixPath(name).parts
                ):
                    raise WorkbookError("unsupported workbook part")
                if name.endswith(".rels"):
                    root = ElementTree.fromstring(archive.read(entry))
                    if any(
                        relation.get("TargetMode", "").lower() == "external"
                        for relation in root
                    ):
                        raise WorkbookError("external workbook links are unsupported")
            if b"macroEnabled" in archive.read("[Content_Types].xml"):
                raise WorkbookError("macro-enabled workbooks are unsupported")
            workbook_xml = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            targets = {
                rel.get("Id"): rel.get("Target")
                for rel in rels.findall(f"{PKG_NS}Relationship")
            }
            formulas: dict[int, set[str]] = {}
            numeric_cells: dict[int, dict[str, str]] = {}
            for index, sheet in enumerate(
                workbook_xml.findall(f"{SHEET_NS}sheets/{SHEET_NS}sheet")
            ):
                target = targets.get(sheet.get(f"{REL_NS}id"))
                if target is None:
                    raise WorkbookError("missing worksheet")
                path = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
                if ".." in PurePosixPath(path).parts:
                    raise WorkbookError("unsupported worksheet path")
                root = ElementTree.fromstring(archive.read(path))
                formulas[index] = {
                    cell.attrib["r"]
                    for cell in root.iter(f"{SHEET_NS}c")
                    if cell.find(f"{SHEET_NS}f") is not None and "r" in cell.attrib
                }
                numeric_cells[index] = {
                    cell.attrib["r"]: value.text
                    for cell in root.iter(f"{SHEET_NS}c")
                    if "r" in cell.attrib and cell.get("t", "n") == "n"
                    if (value := cell.find(f"{SHEET_NS}v")) is not None
                    if value.text is not None
                }
            return formulas, numeric_cells
    except (
        BadZipFile,
        KeyError,
        ElementTree.ParseError,
        OSError,
        NotImplementedError,
        RuntimeError,
        zlib.error,
    ):
        raise WorkbookError("corrupt or unsupported workbook") from None


def _cell_ref(column: int, row: int) -> str:
    result = ""
    column += 1
    while column:
        column, remainder = divmod(column - 1, 26)
        result = chr(65 + remainder) + result
    return f"{result}{row}"


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise WorkbookError("invalid descriptive field")
    return value if value.strip() else None


def _date(value: object) -> date:
    if isinstance(value, datetime):
        if value.time() != time.min:
            raise WorkbookError("invalid date")
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value.strip(), "%d/%m/%Y").date()
        except ValueError:
            pass
    raise WorkbookError("invalid date")


def _amount(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise WorkbookError("invalid amount")
    try:
        text = str(value).strip().replace(",", ".")
        if len(text) > 128:
            raise WorkbookError("invalid amount")
        amount = Decimal(text)
        if not amount.is_finite():
            raise WorkbookError("invalid amount")
        sign, digits, exponent = amount.as_tuple()
        coefficient = int("".join(str(digit) for digit in digits))
        if coefficient == 0:
            return 0
        if not isinstance(exponent, int):
            raise WorkbookError("invalid amount")
        exponent += 2
        if exponent > 20 or exponent < -128:
            raise WorkbookError("amount out of range or precision")
        if exponent < 0:
            result, remainder = divmod(coefficient, 10 ** (-exponent))
            if remainder:
                raise WorkbookError("invalid amount precision")
        else:
            result = coefficient * 10**exponent
        if sign:
            result = -result
        if not -(2**63) <= result < 2**63:
            raise WorkbookError("amount out of range")
        return result
    except InvalidOperation, ValueError:
        raise WorkbookError("invalid amount") from None


def parse_workbook(data: bytes) -> list[Observation]:
    """Parse bytes already read from an XLSX; raise sanitized validation errors."""
    observations, _ = _parse_workbook(data)
    return observations


def _parse_workbook(data: bytes) -> tuple[list[Observation], str | None]:
    formulas, numeric_cells = _validate_archive(data)
    try:
        with CalamineWorkbook.from_filelike(BytesIO(data)) as workbook:
            tables: list[
                tuple[int, int, Sequence[Sequence[object]], dict[str, int]]
            ] = []
            for index in range(len(workbook.sheet_names)):
                rows: Sequence[Sequence[object]] = workbook.get_sheet_by_index(
                    index
                ).to_python(skip_empty_area=False)
                for row_index, row in enumerate(rows):
                    normalized = [_text(cell).casefold() for cell in row]
                    if all(heading in normalized for heading in HEADINGS):
                        if any(normalized.count(heading) != 1 for heading in HEADINGS):
                            raise WorkbookError("duplicate table heading")
                        tables.append(
                            (
                                index,
                                row_index,
                                rows,
                                {h: normalized.index(h) for h in HEADINGS},
                            )
                        )
            if len(tables) != 1:
                raise WorkbookError("missing or ambiguous transaction table")
            index, header_row, rows, columns = tables[0]
            accounts: set[str] = set()
            for row_index, cells in enumerate(rows[:header_row]):
                for column, value in enumerate(cells):
                    if _text(value).casefold() not in (
                        "conti e carte:",
                        "conto o carta:",
                    ):
                        continue
                    reference = cells[column + 1] if column + 1 < len(cells) else ""
                    if _cell_ref(column + 1, row_index + 1) in formulas.get(
                        index, set()
                    ):
                        raise WorkbookError(
                            f"formula in account header at row {row_index + 1}"
                        )
                    if reference not in ("", None):
                        if not isinstance(reference, str):
                            raise WorkbookError(
                                f"invalid account header at row {row_index + 1}"
                            )
                        normalized = " ".join(reference.split())
                        if normalized:
                            accounts.add(normalized)
            transaction_columns = {
                _cell_ref(column, 1)[:-1] for column in columns.values()
            }
            formula_rows: list[int] = []
            for ref in formulas.get(index, set()):
                match = re.fullmatch(r"([A-Z]+)([1-9][0-9]*)", ref)
                if match and match.group(1) in transaction_columns:
                    row_number = int(match.group(2))
                    if row_number > header_row + 1:
                        formula_rows.append(row_number)
            if formula_rows:
                raise WorkbookError(
                    f"formula in transaction cell at row {min(formula_rows)}"
                )
            observations: list[Observation] = []
            footer_start: int | None = None
            for row_index, cells in enumerate(rows[header_row + 1 :], header_row + 1):
                row_number = row_index + 1
                values = {
                    name: cells[column] if column < len(cells) else ""
                    for name, column in columns.items()
                }
                populated = [
                    (name, value)
                    for name, value in values.items()
                    if value not in ("", None)
                ]
                if not populated:
                    continue
                if len(populated) == 1:
                    name, value = populated[0]
                    if (
                        name in ("data", "operazione")
                        and isinstance(value, str)
                        and value.strip()
                        .casefold()
                        .startswith(("nota:", "note:", "legenda:", "avvertenza:"))
                    ):
                        if footer_start is None:
                            footer_start = row_number
                        continue
                if footer_start is not None:
                    raise WorkbookError(f"invalid required field at row {footer_start}")
                account = " ".join(_text(values["conto o carta"]).split())
                status = _text(values["contabilizzazione"]).upper()
                currency = _text(values["valuta"]).upper()
                if not account or status not in (
                    "CONTABILIZZATO",
                    "NON CONTABILIZZATO",
                ):
                    raise WorkbookError(f"invalid required field at row {row_number}")
                if currency != "EUR":
                    raise WorkbookError(f"unsupported currency at row {row_number}")
                try:
                    transaction_date = _date(values["data"])
                    amount_value = numeric_cells[index].get(
                        _cell_ref(columns["importo"], row_number), values["importo"]
                    )
                    amount_minor = _amount(amount_value)
                    operation = _optional_text(values["operazione"])
                    details = _optional_text(values["dettagli"])
                    category = _optional_text(values["categoria"])
                except WorkbookError as exc:
                    raise WorkbookError(f"{exc} at row {row_number}") from None
                accounts.add(account)
                observations.append(
                    Observation(
                        sheet_index=index,
                        row_number=row_number,
                        account_reference=account,
                        transaction_date=transaction_date,
                        amount_minor=amount_minor,
                        currency=currency,
                        operation=operation,
                        details=details,
                        booking_status="booked"
                        if status == "CONTABILIZZATO"
                        else "pending",
                        category=category.strip() if category else None,
                    )
                )
            if len(accounts) > 1:
                raise WorkbookError("multiple accounts")
            return observations, next(iter(accounts), None)
    except CalamineError:
        raise WorkbookError("corrupt or unsupported workbook") from None
