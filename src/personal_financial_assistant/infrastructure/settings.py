"""Load local application settings without exposing connection secrets."""

import asyncio
from ipaddress import ip_address

from pydantic import SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PFA_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: SecretStr

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        try:
            url = make_url(value.get_secret_value())
        except ArgumentError:
            raise ValueError("Invalid database URL") from None
        if (
            url.drivername != "postgresql+asyncpg"
            or not url.host
            or not url.database
            or "host" in url.query
            or "hostaddr" in url.query
        ):
            raise ValueError("Expected an async PostgreSQL URL")
        if url.host.lower() != "localhost":
            try:
                local = ip_address(url.host).is_loopback
            except ValueError:
                local = False
            if not local:
                raise ValueError("Expected a local PostgreSQL URL")
        return value


class SettingsError(Exception):
    """A sanitized configuration error."""


async def load_settings() -> Settings:
    """Read environment and local dotenv settings outside the event loop."""
    try:
        return await asyncio.to_thread(Settings.model_validate, {})
    except ValidationError as exc:
        fields = ", ".join(sorted({str(error["loc"][0]) for error in exc.errors()}))
        raise SettingsError(f"Invalid or missing settings: {fields}") from None
    except OSError, UnicodeError:
        raise SettingsError("Unable to read local configuration") from None
