"""Local, read-only transaction HTTP contracts."""

import re
from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.ext.asyncio import AsyncEngine

from personal_financial_assistant.transactions import (
    TransactionDetail,
    TransactionFilters,
    TransactionPage,
    categories,
    detail,
    search,
)

from .errors import StorageUnavailable

router = APIRouter(prefix="/api/transactions")


class DetailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str

    @field_validator("id")
    @classmethod
    def valid_id(cls, value: str) -> str:
        if not re.fullmatch(r"[1-9][0-9]{0,18}", value) or int(value) > 2**63 - 1:
            raise ValueError("Invalid occurrence ID")
        return value


class CategoriesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _engine(request: Request) -> AsyncEngine:
    engine = cast(AsyncEngine | None, request.app.state.engine)
    if engine is None:
        raise StorageUnavailable
    return engine


@router.post("/search")
async def search_transactions(
    body: TransactionFilters, request: Request
) -> TransactionPage:
    try:
        return await search(_engine(request), body)
    except OSError:
        raise StorageUnavailable from None


@router.post("/detail", response_model=None)
async def transaction_detail(
    body: DetailRequest, request: Request
) -> TransactionDetail | JSONResponse:
    try:
        result = await detail(_engine(request), int(body.id))
    except OSError:
        raise StorageUnavailable from None
    if result is None:
        return JSONResponse(
            {"error": {"code": "not_found", "message": "Transaction not found."}},
            status_code=404,
        )
    return result


@router.post("/categories")
async def transaction_categories(
    body: CategoriesRequest, request: Request
) -> dict[str, list[str]]:
    try:
        return {"categories": await categories(_engine(request))}
    except OSError:
        raise StorageUnavailable from None
