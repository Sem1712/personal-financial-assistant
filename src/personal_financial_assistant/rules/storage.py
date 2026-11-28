"""Transactions and lock ordering for local rule operations."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from personal_financial_assistant.infrastructure.database import (
    PinnedConnectionBusy,
    PinnedConnectionLost,
)
from personal_financial_assistant.infrastructure.models import RulesConfiguration
from personal_financial_assistant.transactions import lock_occurrence

from .types import RuleValidationError, validate_id


class RulesStorageError(Exception):
    """The rule transaction could not complete or be rolled back."""


class RulesLockTimeout(RulesStorageError):
    """The rule transaction could not acquire its locks within five seconds."""


class RulesCommitUnknown(Exception):
    """The commit may have succeeded; read current state before retrying."""


class RulesCommitCancelled(asyncio.CancelledError):
    """Cancellation interrupted a commit whose outcome must be inspected."""


async def commit_rules_transaction(session: AsyncSession) -> None:
    """Commit once; a lost acknowledgement or cancellation has an unknown outcome."""
    try:
        await session.commit()
    except asyncio.CancelledError:
        raise RulesCommitCancelled(
            "Commit outcome unknown; read current state before retrying"
        ) from None
    except SQLAlchemyError, OSError:
        raise RulesCommitUnknown(
            "Commit outcome unknown; read current state before retrying"
        ) from None


async def _rollback(session: AsyncSession) -> None:
    try:
        await session.rollback()
    except SQLAlchemyError, OSError:
        raise RulesStorageError("Could not roll back rule transaction") from None


@asynccontextmanager
async def _transaction(
    bind: AsyncEngine | AsyncConnection,
    occurrence_id: int | None,
    *,
    lock_configuration: bool,
) -> AsyncGenerator[AsyncSession]:
    if occurrence_id is not None and (
        type(occurrence_id) is not int or occurrence_id <= 0
    ):
        raise RuleValidationError("Invalid occurrence ID")
    if isinstance(bind, AsyncConnection) and (bind.closed or bind.invalidated):
        raise PinnedConnectionLost("Pinned database connection unavailable.")
    if isinstance(bind, AsyncConnection) and bind.in_transaction():
        raise PinnedConnectionBusy(
            "Pinned database connection has an active transaction."
        )

    async with AsyncSession(bind, expire_on_commit=False) as session:
        ready_to_commit = False
        try:
            await session.execute(text("SET LOCAL lock_timeout = '5s'"))
            if lock_configuration:
                configuration = await session.scalar(
                    select(RulesConfiguration)
                    .where(RulesConfiguration.id == 1)
                    .with_for_update()
                )
                if configuration is None:
                    raise RulesStorageError("Rules configuration is missing")
            if occurrence_id is not None:
                await lock_occurrence(session, occurrence_id)
            yield session
            await session.flush()
            ready_to_commit = True
        except (SQLAlchemyError, OSError) as error:
            if (
                isinstance(error, DBAPIError)
                and getattr(error.orig, "sqlstate", None) == "55P03"
            ):
                raise RulesLockTimeout("Timed out waiting for rule lock") from None
            raise RulesStorageError("Could not complete rule transaction") from None
        finally:
            if not ready_to_commit:
                await _rollback(session)
        await commit_rules_transaction(session)


@asynccontextmanager
async def rules_transaction(
    bind: AsyncEngine | AsyncConnection, *, occurrence_id: int | None = None
) -> AsyncGenerator[AsyncSession]:
    """Own one transaction, locking configuration before the optional occurrence.

    The caller must not commit or roll back the yielded session. A pinned connection
    remains caller-owned and must be valid and outside any transaction.
    """
    async with _transaction(bind, occurrence_id, lock_configuration=True) as session:
        yield session


@asynccontextmanager
async def occurrence_transaction(
    bind: AsyncEngine | AsyncConnection, occurrence_id: int
) -> AsyncGenerator[AsyncSession]:
    """Own one occurrence-only transaction for user-directed overrides."""
    validate_id(occurrence_id)
    async with _transaction(bind, occurrence_id, lock_configuration=False) as session:
        yield session
