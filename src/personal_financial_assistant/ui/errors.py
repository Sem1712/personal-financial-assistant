"""Sanitized HTTP errors for the local interface."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from .import_coordinator import (
    CoordinatorUnavailable,
    ImportConflict,
    ImportNotStarted,
    ImportRequestClosed,
)
from .security import SECURITY_HEADERS

logger = logging.getLogger(__name__)


class SanitizedServerErrors(logging.Filter):
    """Keep server exception tracebacks from exposing request data."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info:
            record.msg = "Server request failed."
            record.args = ()
            record.exc_info = None
            record.exc_text = None
            record.stack_info = None
        return True


class StorageUnavailable(Exception):
    """Storage is not configured for this application instance."""


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ImportConflict)
    async def import_conflict(_request: Request, _exc: ImportConflict) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": "import_conflict", "message": "An import is running."}},
            status_code=409,
        )

    @app.exception_handler(ImportRequestClosed)
    async def import_request_closed(
        _request: Request, _exc: ImportRequestClosed
    ) -> JSONResponse:
        return JSONResponse(
            {
                "error": {
                    "code": "import_request_closed",
                    "message": "Import request ID is already recorded.",
                }
            },
            status_code=409,
        )

    @app.exception_handler(CoordinatorUnavailable)
    async def coordinator_unavailable(
        _request: Request, _exc: CoordinatorUnavailable
    ) -> JSONResponse:
        return JSONResponse(
            {
                "error": {
                    "code": "coordinator_unavailable",
                    "message": "Import status is unavailable.",
                }
            },
            status_code=503,
        )

    @app.exception_handler(ImportNotStarted)
    async def import_not_started(
        _request: Request, _exc: ImportNotStarted
    ) -> JSONResponse:
        return JSONResponse(
            {
                "error": {
                    "code": "import_not_started",
                    "message": "Storage or import ownership is unavailable.",
                }
            },
            status_code=503,
        )

    @app.exception_handler(StorageUnavailable)
    async def storage_unavailable(
        _request: Request, _exc: StorageUnavailable
    ) -> JSONResponse:
        return JSONResponse(
            {
                "error": {
                    "code": "storage_unavailable",
                    "message": "Storage unavailable.",
                }
            },
            status_code=503,
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_unavailable(
        request: Request, _exc: SQLAlchemyError
    ) -> JSONResponse:
        logger.warning("UI storage is unavailable.")
        return await storage_unavailable(request, StorageUnavailable())

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        _request: Request, _exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": "invalid_input", "message": "Invalid input."}},
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def unexpected_error(_request: Request, _exc: Exception) -> JSONResponse:
        logger.error("Unexpected UI error.")
        return JSONResponse(
            {
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected error occurred.",
                }
            },
            status_code=500,
            headers=SECURITY_HEADERS,
        )
