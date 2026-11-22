from personal_financial_assistant.ingestion.identity import Evidence, plan_group


def test_identical_snapshots_use_maximum_multiplicity() -> None:
    rows = [
        Evidence(1, "a", "pending"),
        Evidence(2, "a", "pending"),
        Evidence(3, "b", "pending"),
    ]
    plan = plan_group([], rows)
    assert len(plan.create) == 2
    assert plan.unresolved == {3}
    assert plan == plan_group([], list(reversed(rows)))


def test_one_to_one_pending_reconciles_even_when_order_changes() -> None:
    rows = [Evidence(1, "a", "pending"), Evidence(2, "b", "booked")]
    plan = plan_group([], rows)
    assert plan.create == [(1, "booked")]
    assert plan.new_links == [(0, 2)]
    assert not plan.unresolved
    assert plan == plan_group([], list(reversed(rows)))


def test_ambiguous_booking_stays_unlinked() -> None:
    rows = [Evidence(3, "new", "booked")]
    plan = plan_group([(10, "pending"), (11, "pending")], rows)
    assert not plan.updates and not plan.links and not plan.create
    assert plan.unresolved == {3}


def test_booked_never_reverts() -> None:
    plan = plan_group([(10, "booked")], [Evidence(3, "new", "pending")])
    assert not plan.updates
    assert plan.links == [(10, 3)]


def test_extra_ambiguous_booking_has_no_invented_status_or_link() -> None:
    plan = plan_group(
        [(10, "pending")], [Evidence(1, "new", "booked"), Evidence(2, "new", "booked")]
    )
    assert plan.create == [(None, None)]
    assert plan.unresolved == {1, 2}
    assert not plan.updates
    assert not plan.links and not plan.new_links


def test_extra_occurrence_does_not_depend_on_row_order_or_existing_status() -> None:
    rows = [Evidence(1, "new", "booked"), Evidence(2, "new", "booked")]
    for existing in ("pending", "booked"):
        plan = plan_group([(10, existing)], rows)
        assert plan.create == [(None, None)]
        assert plan.unresolved == {1, 2}
        assert plan == plan_group([(10, existing)], list(reversed(rows)))
