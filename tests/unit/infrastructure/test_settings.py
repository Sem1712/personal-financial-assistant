from pathlib import Path

import pytest

from personal_financial_assistant.infrastructure.settings import (
    Settings,
    SettingsError,
    load_settings,
)


@pytest.mark.asyncio
async def test_environment_precedes_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "PFA_DATABASE_URL=postgresql+asyncpg://user:file@localhost/file\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "PFA_DATABASE_URL", "postgresql+asyncpg://user:environment@localhost/env"
    )
    settings = await load_settings()
    assert settings.database_url.get_secret_value().endswith("@localhost/env")
    assert "environment" not in repr(settings)


@pytest.mark.asyncio
async def test_dotenv_from_current_directory_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text(
        "PFA_DATABASE_URL=postgresql+asyncpg://user:secret@localhost/db\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("PFA_DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)
    assert (await load_settings()).database_url.get_secret_value().endswith("/db")
    child = tmp_path / "child"
    child.mkdir()
    monkeypatch.chdir(child)
    with pytest.raises(SettingsError, match="database_url"):
        await load_settings()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value",
    [
        "not-a-url-secret",
        "sqlite:///secret",
        "postgresql+asyncpg://user:secret@remote.example/db",
        "postgresql+asyncpg://user:secret@192.0.2.1/db",
        "postgresql+asyncpg://user:secret@localhost/db?host=remote.example",
    ],
)
async def test_invalid_settings_are_redacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PFA_DATABASE_URL", value)
    with pytest.raises(SettingsError) as error:
        await load_settings()
    assert "database_url" in str(error.value)
    assert value not in str(error.value)
    assert Settings.model_fields["database_url"].annotation is not None
