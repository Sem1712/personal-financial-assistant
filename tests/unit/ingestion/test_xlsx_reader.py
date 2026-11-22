from datetime import date
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from personal_financial_assistant.ingestion import xlsx_reader
from personal_financial_assistant.ingestion.xlsx_reader import (
    WorkbookError,
    discover_workbooks,
    parse_workbook,
    read_workbook,
)
from tests.fixtures.intesa_xlsx import HEADINGS, workbook


def row(
    *,
    day: str = "22/11/2026",
    account: str = "SYNTHETIC",
    status: str = "CONTABILIZZATO",
    currency: str = "EUR",
    amount: str | float = "-12.34",
) -> list[str | float]:
    return [
        day,
        "Operation",
        "Details",
        account,
        status,
        " Category ",
        currency,
        amount,
    ]


def test_header_discovery_rows_and_exact_values() -> None:
    data = workbook(
        [
            ["Export"],
            ["Preamble"],
            [f" {heading} " for heading in HEADINGS],
            row(),
            row(status="NON CONTABILIZZATO", amount=10.05),
            [],
            ["", "Nota: explanatory footer"],
            ["Legenda: explanatory footer"],
        ]
    )
    observations = parse_workbook(data)
    assert len(observations) == 2
    assert observations[0].transaction_date == date(2026, 11, 22)
    assert observations[0].amount_minor == -1234
    assert observations[0].category == "Category"
    assert observations[0].booking_status == "booked"
    assert observations[1].amount_minor == 1005
    assert observations[1].booking_status == "pending"


def test_date_formatted_excel_serial_is_read_as_a_date() -> None:
    values = row()
    data: list[str | float | int] = list(values)
    data[0] = (date(2026, 11, 22) - date(1899, 12, 30)).days
    original = workbook([HEADINGS, data])
    output = BytesIO()
    styles = (
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="1"><font/></fonts><fills count="1"><fill/></fills>'
        '<borders count="1"><border/></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="14" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs>'
        "</styleSheet>"
    )
    with (
        ZipFile(BytesIO(original)) as source,
        ZipFile(output, "w", ZIP_DEFLATED) as result,
    ):
        for item in source.infolist():
            contents = source.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                contents = contents.replace(b'<c r="A2">', b'<c r="A2" s="1">')
            elif item.filename == "xl/_rels/workbook.xml.rels":
                contents = contents.replace(
                    b"</Relationships>",
                    b'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
                )
            result.writestr(item.filename, contents)
        result.writestr("xl/styles.xml", styles)
    assert parse_workbook(output.getvalue())[0].transaction_date == date(2026, 11, 22)


@pytest.mark.parametrize(
    "values",
    [
        row(day="not a date"),
        row(account=""),
        row(status="unknown"),
        row(currency="USD"),
        row(currency=""),
        row(amount="0.001"),
        row(amount="invalid"),
    ],
)
def test_invalid_transaction_row_is_rejected(values: list[str | float]) -> None:
    with pytest.raises(WorkbookError):
        parse_workbook(workbook([HEADINGS, values]))


def test_unsupported_layout_is_rejected() -> None:
    with pytest.raises(WorkbookError):
        parse_workbook(workbook([["Unexpected heading"], row()]))


def test_multiple_identical_rows_are_preserved() -> None:
    observations = parse_workbook(workbook([HEADINGS, row(), row()]))
    assert len(observations) == 2


def test_numeric_cell_uses_exact_xml_value_not_binary_float() -> None:
    original = workbook([HEADINGS, row(amount=1.0)])
    output = BytesIO()
    with (
        ZipFile(BytesIO(original)) as source,
        ZipFile(output, "w", ZIP_DEFLATED) as result,
    ):
        for item in source.infolist():
            contents = source.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                contents = contents.replace(b"<v>1.0</v>", b"<v>90071992547409.91</v>")
            result.writestr(item.filename, contents)
    assert parse_workbook(output.getvalue())[0].amount_minor == 9007199254740991


def test_long_subcent_fraction_is_not_rounded_away() -> None:
    with pytest.raises(WorkbookError, match="precision"):
        parse_workbook(
            workbook([HEADINGS, row(amount="1.00000000000000000000000000001")])
        )


def test_multiple_accounts_are_rejected() -> None:
    with pytest.raises(WorkbookError):
        parse_workbook(workbook([HEADINGS, row(), row(account="OTHER")]))


def test_preamble_account_must_match_transaction_account() -> None:
    data = workbook([["", "Conti e Carte:", "OTHER"], HEADINGS, row()])
    with pytest.raises(WorkbookError, match="account") as exc:
        parse_workbook(data)
    assert "OTHER" not in str(exc.value)


def test_conflicting_preamble_accounts_are_rejected_even_when_empty() -> None:
    data = workbook(
        [["", "Conti e Carte:", "SYNTHETIC"], ["", "Conti e Carte:", "OTHER"], HEADINGS]
    )
    with pytest.raises(WorkbookError, match="account"):
        parse_workbook(data)


@pytest.mark.asyncio
async def test_empty_workbook_retains_identifiable_preamble_account(
    tmp_path: Path,
) -> None:
    (tmp_path / "empty.xlsx").write_bytes(
        workbook([["", "Conti e Carte:", " SYNTHETIC "], HEADINGS])
    )
    snapshot = (await discover_workbooks(tmp_path))[0]
    parsed = await read_workbook(snapshot)
    assert parsed.account_reference == "SYNTHETIC"
    assert parsed.observations == []


def test_required_formula_is_rejected_even_with_cached_value() -> None:
    original = workbook([HEADINGS, row(amount=-12.34)])
    output = BytesIO()
    with (
        ZipFile(BytesIO(original)) as source,
        ZipFile(output, "w", ZIP_DEFLATED) as result,
    ):
        for item in source.infolist():
            contents = source.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                contents = contents.replace(
                    b"<v>-12.34</v>", b"<f>1+1</f><v>-12.34</v>"
                )
            result.writestr(item.filename, contents)
    with pytest.raises(WorkbookError, match="formula"):
        parse_workbook(output.getvalue())


def test_required_formula_without_cached_value_is_rejected() -> None:
    original = workbook([HEADINGS, row(amount=1.0)])
    output = BytesIO()
    with (
        ZipFile(BytesIO(original)) as source,
        ZipFile(output, "w", ZIP_DEFLATED) as result,
    ):
        for item in source.infolist():
            contents = source.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                contents = contents.replace(b"<v>1.0</v>", b"<f>1+1</f>")
            result.writestr(item.filename, contents)
    with pytest.raises(WorkbookError, match="formula"):
        parse_workbook(output.getvalue())


def test_required_formula_only_row_without_cached_value_is_rejected() -> None:
    original = workbook([HEADINGS, []])
    output = BytesIO()
    with (
        ZipFile(BytesIO(original)) as source,
        ZipFile(output, "w", ZIP_DEFLATED) as result,
    ):
        for item in source.infolist():
            contents = source.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                contents = contents.replace(
                    b'<row r="2"></row>',
                    b'<row r="2"><c r="H2"><f>1+1</f></c></row>',
                )
            result.writestr(item.filename, contents)
    with pytest.raises(WorkbookError, match="formula.*row 2"):
        parse_workbook(output.getvalue())


def test_descriptive_formula_without_cached_value_is_rejected() -> None:
    original = workbook([HEADINGS, row()])
    output = BytesIO()
    with (
        ZipFile(BytesIO(original)) as source,
        ZipFile(output, "w", ZIP_DEFLATED) as result,
    ):
        for item in source.infolist():
            contents = source.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                contents = contents.replace(
                    b'<c r="C2" t="inlineStr"><is><t xml:space="preserve">Details</t></is></c>',
                    b'<c r="C2"><f>1+1</f></c>',
                )
            result.writestr(item.filename, contents)
    with pytest.raises(WorkbookError, match="formula.*row 2"):
        parse_workbook(output.getvalue())


def test_incomplete_transaction_with_multiple_descriptive_fields_fails() -> None:
    with pytest.raises(WorkbookError, match="required"):
        parse_workbook(workbook([HEADINGS, ["", "Operation", "Details"]]))


@pytest.mark.parametrize("column", [1, 2, 5])
@pytest.mark.parametrize("value", [123, 1.5])
def test_nontext_descriptive_values_are_rejected(column: int, value: float) -> None:
    values: list[str | float | int] = list(row())
    values[column] = value
    with pytest.raises(WorkbookError, match="descriptive field at row 2") as exc:
        parse_workbook(workbook([HEADINGS, values]))
    assert str(value) not in str(exc.value)


def test_boolean_descriptive_value_is_rejected() -> None:
    values: list[str | float | int] = list(row())
    values[2] = 1
    original = workbook([HEADINGS, values])
    output = BytesIO()
    with (
        ZipFile(BytesIO(original)) as source,
        ZipFile(output, "w", ZIP_DEFLATED) as result,
    ):
        for item in source.infolist():
            contents = source.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                contents = contents.replace(
                    b'<c r="C2"><v>1</v></c>', b'<c r="C2" t="b"><v>1</v></c>'
                )
            result.writestr(item.filename, contents)
    with pytest.raises(WorkbookError, match="descriptive field at row 2"):
        parse_workbook(output.getvalue())


@pytest.mark.parametrize(
    "values",
    [
        ["invalid date"],
        ["", "Operation"],
        ["", "", "Details"],
        ["", "", "", "ACCOUNT"],
        ["", "", "", "", "CONTABILIZZATO"],
        ["", "", "", "", "", "Category"],
        ["", "", "", "", "", "", "EUR"],
        ["", "", "", "", "", "", "", "-12.34"],
    ],
)
def test_ambiguous_single_field_rows_fail(values: list[str]) -> None:
    with pytest.raises(WorkbookError, match="row 2"):
        parse_workbook(workbook([HEADINGS, values]))


@pytest.mark.parametrize(
    "values",
    [
        [HEADINGS, ["", "Nota: possible operation"], row()],
        [HEADINGS, row(), ["Legenda: possible operation"], [], row()],
    ],
)
def test_note_shaped_row_before_transaction_is_not_a_footer(
    values: list[list[str | float]],
) -> None:
    with pytest.raises(WorkbookError, match="required field at row"):
        parse_workbook(workbook(values))


def test_corrupt_workbook_is_rejected() -> None:
    with pytest.raises(WorkbookError):
        parse_workbook(b"not an xlsx")


@pytest.mark.parametrize(
    "limit", ["MAX_FILE_SIZE", "MAX_EXPANDED_SIZE", "MAX_ENTRIES", "MAX_RATIO"]
)
def test_safety_limits_are_enforced(
    monkeypatch: pytest.MonkeyPatch, limit: str
) -> None:
    monkeypatch.setattr(xlsx_reader, limit, 0)
    with pytest.raises(WorkbookError):
        parse_workbook(workbook([HEADINGS, row()]))


def test_compressed_size_limit_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    data = workbook([HEADINGS, row()])
    monkeypatch.setattr(xlsx_reader, "MAX_FILE_SIZE", len(data))
    assert len(parse_workbook(data)) == 1
    monkeypatch.setattr(xlsx_reader, "MAX_FILE_SIZE", len(data) - 1)
    with pytest.raises(WorkbookError, match="size limit"):
        parse_workbook(data)


@pytest.mark.parametrize("part", ["xl/vbaProject.bin", "xl/externalLinks/link.xml"])
def test_unsupported_workbook_parts_are_rejected(part: str) -> None:
    source_bytes = workbook([HEADINGS, row()])
    output = BytesIO()
    with (
        ZipFile(BytesIO(source_bytes)) as source,
        ZipFile(output, "w", ZIP_DEFLATED) as result,
    ):
        for item in source.infolist():
            result.writestr(item.filename, source.read(item.filename))
        result.writestr(part, "unsupported")
    with pytest.raises(WorkbookError):
        parse_workbook(output.getvalue())


@pytest.mark.asyncio
async def test_discovery_ignores_symlinks_temporary_files_and_subdirectories(
    tmp_path: Path,
) -> None:
    data = workbook([HEADINGS, row()])
    (tmp_path / "valid.xlsx").write_bytes(data)
    (tmp_path / "~$lock.xlsx").write_bytes(data)
    (tmp_path / "link.xlsx").symlink_to(tmp_path / "valid.xlsx")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "hidden.xlsx").write_bytes(data)
    snapshots = await discover_workbooks(tmp_path)
    assert [item.path.name for item in snapshots] == ["valid.xlsx"]
    assert len((await read_workbook(snapshots[0])).observations) == 1


@pytest.mark.asyncio
async def test_changed_file_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "valid.xlsx"
    target.write_bytes(workbook([HEADINGS, row()]))
    snapshots = await discover_workbooks(tmp_path)
    target.write_bytes(workbook([HEADINGS, row(), row()]))
    with pytest.raises(WorkbookError):
        await read_workbook(snapshots[0])


@pytest.mark.asyncio
async def test_missing_directory_is_a_sanitized_error(tmp_path: Path) -> None:
    with pytest.raises(WorkbookError, match="input directory"):
        await discover_workbooks(tmp_path / "private-name")
