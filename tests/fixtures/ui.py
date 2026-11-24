"""Synthetic inputs for local UI tests."""

from pathlib import Path

from tests.fixtures.intesa_xlsx import HEADINGS, workbook


def create_export(directory: Path) -> Path:
    """Create one synthetic supported workbook in an existing folder."""
    path = directory / "synthetic.xlsx"
    path.write_bytes(
        workbook(
            [
                HEADINGS,
                [
                    "01/01/2025",
                    "Synthetic purchase",
                    "Example",
                    "TEST-ACCOUNT",
                    "CONTABILIZZATO",
                    "Food",
                    "EUR",
                    -12.34,
                ],
            ]
        )
    )
    return path
