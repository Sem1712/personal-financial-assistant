from datetime import date, timedelta

import pytest
from sqlalchemy import insert, update
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from personal_financial_assistant.infrastructure.models import (
    SelectedAccount,
    SourceFile,
    TransactionObservation,
    TransactionOccurrence,
    occurrence_observation,
)
from personal_financial_assistant.transactions.filters import TransactionFilters
from personal_financial_assistant.transactions.service import categories, detail, search


async def populate(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            insert(SelectedAccount).values(id=1, account_reference="synthetic")
        )
        await connection.execute(
            insert(SourceFile).values(
                sha256="a" * 64, account_id=1, transaction_row_count=2
            )
        )
        await connection.execute(
            insert(TransactionObservation),
            [
                {
                    "id": index,
                    "source_file_sha256": "a" * 64,
                    "sheet_index": 0,
                    "row_number": index,
                    "account_id": 1,
                    "transaction_date": date(2025, 1, 15),
                    "amount_minor": -500,
                    "currency": "EUR",
                    "operation": operation,
                    "details": f"Recorded detail {index}",
                    "booking_status": "booked",
                    "category": category,
                    "candidate_key": "b" * 64,
                    "occurrence_ordinal": index,
                }
                for index, operation, category in (
                    (1, r"Coffee 100%_deal\special", "Food"),
                    (2, "Other source", "Travel"),
                )
            ],
        )
        records: list[dict[str, object]] = [
            {
                "id": index,
                "account_id": 1,
                "transaction_date": (
                    date(2025, 1, 15)
                    if index <= 2
                    else date(2025, 1, 1) + timedelta(days=index % 30)
                ),
                "amount_minor": -500
                if index <= 2
                else -index * 100
                if index <= 4
                else index * 100,
                "currency": "EUR",
                "booking_status": (
                    None
                    if index == 2
                    else "pending"
                    if index in (3, 4, 5)
                    else "booked"
                ),
                "reconciliation_state": (
                    "unresolved"
                    if index in (2, 4)
                    else "pending-only"
                    if index == 3
                    else "confirmed"
                ),
            }
            for index in range(1, 106)
        ]
        await connection.execute(insert(TransactionOccurrence), records)
        await connection.execute(
            insert(occurrence_observation),
            [
                {"occurrence_id": 1, "observation_id": 1},
                {"occurrence_id": 1, "observation_id": 2},
            ],
        )


@pytest.mark.asyncio
async def test_history_pagination_and_identical_occurrences(migrated_url: str) -> None:
    engine = create_async_engine(migrated_url)
    try:
        empty = await search(engine, TransactionFilters())
        assert not empty.history_exists
        assert empty.items == []
        await populate(engine)
        default_page = await search(engine, TransactionFilters())
        assert len(default_page.items) == 100
        assert default_page.next_cursor is not None
        last_page = await search(
            engine,
            TransactionFilters.model_validate({"cursor": default_page.next_cursor}),
        )
        assert len(last_page.items) == 5
        assert last_page.next_cursor is None
        assert len({item.id for item in [*default_page.items, *last_page.items]}) == 105
        filters = TransactionFilters.model_validate({"page_size": 20})
        ids: list[str] = []
        while True:
            page = await search(engine, filters)
            assert page.history_exists
            ids.extend(item.id for item in page.items)
            if page.next_cursor is None:
                break
            filters = TransactionFilters.model_validate(
                {"page_size": 20, "cursor": page.next_cursor}
            )
        assert len(ids) == len(set(ids)) == 105
        assert "1" in ids and "2" in ids
        missing = await search(
            engine, TransactionFilters.model_validate({"text": "absent"})
        )
        assert missing.history_exists and not missing.items
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_filters_match_linked_evidence_without_multiplying_occurrences(
    migrated_url: str,
) -> None:
    engine = create_async_engine(migrated_url)
    try:
        await populate(engine)
        filters = TransactionFilters.model_validate(
            {
                "date_from": "2025-01-15",
                "date_to": "2025-01-15",
                "booking_status": "booked",
                "text": r"100%_deal\special",
                "category": {"kind": "value", "value": "Travel"},
                "amount_min": "5.00",
                "amount_max": "5",
            }
        )
        result = await search(engine, filters)
        assert [item.id for item in result.items] == ["1"]
        assert result.items[0].amount_minor == "-500"
        assert result.items[0].operations == [
            r"Coffee 100%_deal\special",
            "Other source",
        ]
        assert result.items[0].details == ["Recorded detail 1", "Recorded detail 2"]
        assert not (
            await search(engine, TransactionFilters.model_validate({"text": "100X"}))
        ).items
        no_category = await search(
            engine,
            TransactionFilters.model_validate(
                {
                    "booking_status": "unknown",
                    "category": {"kind": "no_recorded_category"},
                    "amount_min": "5",
                    "amount_max": "5",
                }
            ),
        )
        assert [item.id for item in no_category.items] == ["2"]
        assert no_category.items[0].operations == []
        assert no_category.items[0].details == []
        pending = await search(
            engine, TransactionFilters.model_validate({"booking_status": "pending"})
        )
        assert {item.id: item.ongoing_expense for item in pending.items} == {
            "3": True,
            "4": False,
            "5": False,
        }
        async with engine.begin() as connection:
            await connection.execute(
                update(TransactionObservation)
                .where(TransactionObservation.id == 2)
                .values(
                    operation=r"Coffee 100%_deal\special", details="Recorded detail 1"
                )
            )
        duplicate_sources = await search(engine, filters)
        assert duplicate_sources.items[0].operations == [r"Coffee 100%_deal\special"]
        assert duplicate_sources.items[0].details == ["Recorded detail 1"]
        async with engine.begin() as connection:
            await connection.execute(
                update(TransactionObservation).values(operation=None, details=None)
            )
        missing_operations = await search(
            engine,
            TransactionFilters.model_validate(
                {"category": {"kind": "value", "value": "Food"}}
            ),
        )
        assert missing_operations.items[0].operations == []
        assert missing_operations.items[0].details == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_absolute_amounts_direction_zero_and_bigint_limits(
    migrated_url: str,
) -> None:
    engine = create_async_engine(migrated_url)
    try:
        await populate(engine)
        async with engine.begin() as connection:
            await connection.execute(
                insert(TransactionOccurrence),
                [
                    {
                        "id": index,
                        "account_id": 1,
                        "transaction_date": date(2026, 1, 1),
                        "amount_minor": amount,
                        "currency": "EUR",
                        "booking_status": "booked",
                        "reconciliation_state": "confirmed",
                    }
                    for index, amount in enumerate(
                        [-(2**63), -501, -500, 0, 500, 501, 2**63 - 1], start=201
                    )
                ],
            )
        date_filters = {"date_from": "2026-01-01", "date_to": "2026-01-01"}
        cases: list[tuple[dict[str, str], set[int]]] = [
            ({"amount_min": "5", "amount_max": "5"}, {203, 205}),
            ({"amount_min": "0", "amount_max": "5"}, {203, 204, 205}),
            ({"amount_max": "0"}, {204}),
            ({"direction": "withdrawals"}, {201, 202, 203}),
            ({"direction": "deposits"}, {205, 206, 207}),
            (
                {"amount_min": "5", "amount_max": "5", "direction": "withdrawals"},
                {203},
            ),
            (
                {"amount_min": "5", "amount_max": "5", "direction": "deposits"},
                {205},
            ),
            (
                {
                    "amount_min": "92233720368547758.08",
                    "amount_max": "92233720368547758.08",
                },
                {201},
            ),
            ({"amount_max": "92233720368547758.08"}, set(range(201, 208))),
        ]
        for criteria, expected in cases:
            result = await search(
                engine, TransactionFilters.model_validate({**date_filters, **criteria})
            )
            assert {int(item.id) for item in result.items} == expected
        criteria = {**date_filters, "direction": "withdrawals", "amount_min": "5"}
        first = await search(
            engine, TransactionFilters.model_validate({**criteria, "page_size": 1})
        )
        assert [item.id for item in first.items] == ["203"]
        assert first.next_cursor is not None
        second = await search(
            engine,
            TransactionFilters.model_validate(
                {**criteria, "page_size": 1, "cursor": first.next_cursor}
            ),
        )
        assert [item.id for item in second.items] == ["202"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_details_preserve_distinct_sources_and_missing_links(
    migrated_url: str,
) -> None:
    engine = create_async_engine(migrated_url)
    try:
        await populate(engine)
        item = await detail(engine, 1)
        assert item is not None
        assert [source.category for source in item.observations] == ["Food", "Travel"]
        assert item.observations[0].operation == r"Coffee 100%_deal\special"
        assert item.operations == [r"Coffee 100%_deal\special", "Other source"]
        assert item.details == ["Recorded detail 1", "Recorded detail 2"]
        unlinked = await detail(engine, 2)
        assert unlinked is not None
        assert unlinked.booking_status == "unknown"
        assert unlinked.observations == []
        assert unlinked.operations == []
        assert unlinked.details == []
        assert await detail(engine, 9999) is None
        assert await categories(engine) == ["Food", "Travel"]
    finally:
        await engine.dispose()
