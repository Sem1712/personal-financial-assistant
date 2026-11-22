"""Conservative reconciliation of observations within a candidate group."""

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Evidence:
    id: int
    source: str
    status: str


@dataclass
class GroupPlan:
    create: list[tuple[int | None, str | None]] = field(
        default_factory=list[tuple[int | None, str | None]]
    )
    links: list[tuple[int, int]] = field(default_factory=list[tuple[int, int]])
    new_links: list[tuple[int, int]] = field(default_factory=list[tuple[int, int]])
    updates: list[tuple[int, str]] = field(default_factory=list[tuple[int, str]])
    unresolved: set[int] = field(default_factory=set[int])


def plan_group(
    existing: list[tuple[int, str | None]], evidence: list[Evidence]
) -> GroupPlan:
    """Keep maximum snapshot multiplicity, linking only unambiguous groups."""
    plan = GroupPlan()
    files: defaultdict[str, list[Evidence]] = defaultdict(list)
    for row in evidence:
        files[row.source].append(row)
    if not files:
        return plan
    for rows in files.values():
        rows.sort(key=lambda row: (row.status != "pending", row.id))
    selected = max(
        sorted(files.items()),
        key=lambda item: (
            len(item[1]),
            sum(row.status == "pending" for row in item[1]),
        ),
    )[1]
    target = max(len(existing), len(selected))
    if target == 1:
        rows = sorted(
            evidence, key=lambda row: (row.status != "pending", row.source, row.id)
        )
        booked = any(row.status == "booked" for row in rows)
        if existing:
            occurrence_id, status = existing[0]
            if status == "pending" and booked:
                plan.updates.append((occurrence_id, "booked"))
            plan.links.extend((occurrence_id, row.id) for row in rows)
        else:
            plan.create.append((rows[0].id, "booked" if booked else "pending"))
            plan.new_links.extend((0, row.id) for row in rows[1:])
        return plan
    extra = max(0, target - len(existing))
    chosen = selected if not existing else []
    for row in chosen:
        plan.create.append((row.id, row.status))
    if existing:
        plan.create.extend((None, None) for _ in range(extra))
    plan.unresolved = {row.id for row in evidence} - {row.id for row in chosen}
    return plan
