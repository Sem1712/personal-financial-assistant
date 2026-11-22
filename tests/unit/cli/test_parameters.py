from pathlib import Path

import pytest
from pydantic import ValidationError

from personal_financial_assistant.cli import (
    IngestXlsxParameters,
    ParameterError,
    parse_parameters,
)


def test_relative_input_directory_remains_relative() -> None:
    params = IngestXlsxParameters(input_dir=Path("exports"))
    assert params.input_dir == Path("exports")


@pytest.mark.parametrize("value", [{}, {"input_dir": None}, {"input_dir": 123}])
def test_invalid_input_directory(value: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        IngestXlsxParameters.model_validate(value)


def test_cli_arguments_accept_relative_path() -> None:
    assert parse_parameters(
        ["ingest-xlsx", "--input-dir", "exports"]
    ).input_dir == Path("exports")


@pytest.mark.parametrize(
    "arguments",
    [[], ["ingest-xlsx"], ["ingest-xlsx", "--input-dir", ""], ["bad-secret-command"]],
)
def test_invalid_cli_arguments_are_sanitized(arguments: list[str]) -> None:
    with pytest.raises(ParameterError) as exc:
        parse_parameters(arguments)
    assert "bad-secret-command" not in str(exc.value)
