import logging

import pytest

from personal_financial_assistant import cli


@pytest.mark.asyncio
async def test_serve_ui_dispatches_without_changing_ingest_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def serve() -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(cli, "serve_ui", serve)
    assert await cli.run(["serve-ui"]) == 0
    assert called


@pytest.mark.asyncio
async def test_serve_ui_rejects_host_override(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert await cli.run(["serve-ui", "--host", "0.0.0.0"]) == 1
    assert "0.0.0.0" not in capsys.readouterr().err


def test_server_exception_log_does_not_expose_sensitive_values() -> None:
    from personal_financial_assistant.ui.errors import SanitizedServerErrors

    record = logging.LogRecord(
        "uvicorn.error",
        logging.ERROR,
        __file__,
        1,
        "private-transaction-value",
        (),
        (RuntimeError, RuntimeError("private-transaction-value"), None),
    )
    assert SanitizedServerErrors().filter(record)
    assert "private-transaction-value" not in record.getMessage()
    assert record.exc_info is None
