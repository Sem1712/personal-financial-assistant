from typing import cast

import pytest
from sqlalchemy import Table, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from personal_financial_assistant.infrastructure.models import (
    ApplicationApproval,
    ApplicationConflict,
    ChangeSuggestion,
    ClassificationPreference,
    Merchant,
    MerchantDefault,
    MerchantMatch,
    OccurrenceEvidenceRevision,
    RuleEvaluationOutcome,
    RuleEvaluationWork,
    RulesConfiguration,
    SelectedAccount,
    TransactionOccurrence,
    TransactionOverride,
)


@pytest.mark.asyncio
async def test_reusable_rule_database_constraints(postgres_url: str) -> None:
    engine = create_async_engine(postgres_url)
    try:
        async with engine.begin() as connection:
            for model in (
                Merchant,
                MerchantMatch,
                MerchantDefault,
                ClassificationPreference,
            ):
                table = cast(Table, model.__table__)
                await connection.run_sync(table.create)

            for statement in (
                "INSERT INTO merchant (id, canonical_name) VALUES (1, 'Shop'), (2, 'Other')",
                (
                    "INSERT INTO merchant_match (merchant_id, kind, original_text, normalized_text, origin) "
                    "VALUES (1, 'alias', 'SHOP', 'shop', 'user'), (2, 'alias', 'Shop', 'shop', 'ai')"
                ),
                (
                    "INSERT INTO merchant_default (merchant_id, category, origin, enabled) "
                    "VALUES (1, 'Food', 'user', false)"
                ),
                (
                    "INSERT INTO classification_preference (match_kind, merchant_id, category, origin) "
                    "VALUES ('merchant', 1, 'Food', 'user')"
                ),
            ):
                await connection.execute(text(statement))

            invalid_statements = (
                "INSERT INTO merchant (canonical_name) VALUES (U&'\\00A0')",
                "INSERT INTO merchant (canonical_name, revision) VALUES ('x', 0)",
                "INSERT INTO merchant (canonical_name, enabled_revision) VALUES ('x', 0)",
                (
                    "INSERT INTO merchant_match (merchant_id, kind, original_text, normalized_text, origin) "
                    "VALUES (1, 'alias', 'shop', 'shop', 'service')"
                ),
                (
                    "INSERT INTO merchant_match (merchant_id, kind, original_text, normalized_text, origin) "
                    "VALUES (1, 'alias', 'x', 'x', 'unknown')"
                ),
                "INSERT INTO merchant_default (merchant_id, category, origin) VALUES (1, 'Other', 'user')",
                "INSERT INTO merchant_default (merchant_id, category, origin) VALUES (2, U&'\\00A0', 'user')",
                (
                    "INSERT INTO classification_preference (match_kind, merchant_id, match_text, category, origin) "
                    "VALUES ('merchant', 1, 'shop', 'Food', 'user')"
                ),
                (
                    "INSERT INTO classification_preference (match_kind, match_text, category, origin) "
                    "VALUES ('exact_description', U&'\\00A0', 'Food', 'user')"
                ),
                "DELETE FROM merchant WHERE id = 1",
            )
            for statement in invalid_statements:
                with pytest.raises(IntegrityError):
                    async with connection.begin_nested():
                        await connection.execute(text(statement))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_evaluation_work_schema_enforces_valid_states(postgres_url: str) -> None:
    engine = create_async_engine(postgres_url)
    try:
        async with engine.begin() as connection:
            for model in (
                SelectedAccount,
                TransactionOccurrence,
                Merchant,
                RulesConfiguration,
                OccurrenceEvidenceRevision,
                RuleEvaluationWork,
                RuleEvaluationOutcome,
            ):
                table = cast(Table, model.__table__)
                await connection.run_sync(table.create)

            for statement in (
                "INSERT INTO selected_account (id, account_reference) VALUES (1, 'synthetic')",
                (
                    "INSERT INTO transaction_occurrence (id, account_id, transaction_date, amount_minor, currency, "
                    "booking_status, reconciliation_state) VALUES (1, 1, '2025-01-01', -100, 'EUR', 'booked', 'confirmed')"
                ),
                "INSERT INTO rules_configuration (id) VALUES (1)",
                "INSERT INTO occurrence_evidence_revision (occurrence_id) VALUES (1)",
                (
                    "INSERT INTO rule_evaluation_work (occurrence_id, import_correlation_id, state) "
                    "VALUES (1, '00000000-0000-0000-0000-000000000001', 'pending')"
                ),
            ):
                await connection.execute(text(statement))

            invalid_statements = (
                "INSERT INTO rules_configuration (id) VALUES (2)",
                "UPDATE occurrence_evidence_revision SET revision = 0",
                "UPDATE rule_evaluation_work SET state = 'unknown'",
                "UPDATE rule_evaluation_work SET state = 'failed'",
                "UPDATE rule_evaluation_work SET last_error_code = 'storage_failure'",
                (
                    "INSERT INTO rule_evaluation_outcome "
                    "(occurrence_id, evidence_revision, merchant_status, merchant_id, "
                    "matching_candidates, category_decision, winning_references, blocked_ai_conflicts) "
                    "VALUES (1, 1, 'resolved', 999, '[]', '{}', '[]', '[]')"
                ),
            )
            for statement in invalid_statements:
                with pytest.raises(IntegrityError):
                    async with connection.begin_nested():
                        await connection.execute(text(statement))

            await connection.execute(
                text(
                    "INSERT INTO rule_evaluation_outcome "
                    "(occurrence_id, evidence_revision, merchant_status, matching_candidates, "
                    "category_decision, winning_references, blocked_ai_conflicts) "
                    "VALUES (1, 1, 'no_match', '[]', '{\"kind\": \"unchanged\"}', '[]', '[]')"
                )
            )
            await connection.execute(
                text("UPDATE rule_evaluation_work SET state = 'completed'")
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_review_schema_enforces_typed_references(postgres_url: str) -> None:
    engine = create_async_engine(postgres_url)
    try:
        async with engine.begin() as connection:
            for model in (
                SelectedAccount,
                TransactionOccurrence,
                Merchant,
                MerchantMatch,
                MerchantDefault,
                ClassificationPreference,
                TransactionOverride,
                ChangeSuggestion,
                ApplicationConflict,
                ApplicationApproval,
            ):
                table = cast(Table, model.__table__)
                await connection.run_sync(table.create)

            for statement in (
                "INSERT INTO selected_account (id, account_reference) VALUES (1, 'synthetic')",
                (
                    "INSERT INTO transaction_occurrence (id, account_id, transaction_date, amount_minor, currency, "
                    "booking_status, reconciliation_state) VALUES (1, 1, '2025-01-01', -100, 'EUR', 'booked', 'confirmed')"
                ),
                "INSERT INTO merchant (id, canonical_name) VALUES (1, 'shop')",
                "INSERT INTO merchant_default (id, merchant_id, category, origin) VALUES (1, 1, 'food', 'ai')",
                (
                    "INSERT INTO classification_preference (id, match_kind, match_text, category, origin) "
                    "VALUES (1, 'exact_description', 'shop', 'other', 'user')"
                ),
                "INSERT INTO transaction_override (occurrence_id, category) VALUES (1, 'food')",
                (
                    "INSERT INTO change_suggestion "
                    "(id, target_kind, target_default_id, target_revision, action, payload, origin, state) "
                    "VALUES (1, 'merchant_default', 1, 1, 'edit', '{}', 'ai', 'pending')"
                ),
                (
                    "INSERT INTO application_conflict "
                    "(id, occurrence_id, ai_kind, ai_default_id, ai_revision, confirmed_kind, "
                    "confirmed_preference_id, confirmed_revision, evidence_revision, outcome_kind, state) "
                    "VALUES (1, 1, 'merchant_default', 1, 1, 'classification_preference', 1, 1, 1, 'category', 'pending')"
                ),
                (
                    "INSERT INTO application_approval "
                    "(conflict_id, ai_revision, confirmed_revision, evidence_revision, merchant_revisions) "
                    "VALUES (1, 1, 1, 1, '[[1, 1]]')"
                ),
            ):
                await connection.execute(text(statement))

            invalid_statements = (
                "INSERT INTO transaction_override (occurrence_id, category) VALUES (1, 'other')",
                "UPDATE transaction_override SET category = U&'\\00A0'",
                "UPDATE change_suggestion SET target_kind = 'classification_preference'",
                "UPDATE change_suggestion SET target_default_id = 999",
                "UPDATE change_suggestion SET origin = 'xx'",
                "UPDATE change_suggestion SET target_preference_id = 1",
                "UPDATE application_conflict SET outcome_kind = 'merchant'",
                "UPDATE application_conflict SET confirmed_preference_id = 999",
                "UPDATE application_conflict SET ai_preference_id = 1",
                "UPDATE application_conflict SET ai_revision = 0",
                "UPDATE application_approval SET evidence_revision = 0",
                "UPDATE application_approval SET merchant_revisions = '{}'::jsonb",
                (
                    "INSERT INTO application_conflict "
                    "(occurrence_id, ai_kind, ai_default_id, ai_revision, confirmed_kind, "
                    "confirmed_preference_id, confirmed_revision, evidence_revision, outcome_kind, state) "
                    "VALUES (1, 'merchant_default', 1, 1, 'classification_preference', 1, 1, 1, 'category', 'pending')"
                ),
            )
            for statement in invalid_statements:
                with pytest.raises(IntegrityError):
                    async with connection.begin_nested():
                        await connection.execute(text(statement))
    finally:
        await engine.dispose()
