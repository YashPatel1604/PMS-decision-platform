"""Reconciliation row types and classifications."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


class Classification:
    IDENTICAL = "identical"
    ONLY_IN_SAMIR = "only_in_samir"
    ONLY_IN_JULESH = "only_in_julesh"
    ONLY_IN_RESEARCH = "only_in_research"
    COMPATIBLE_MERGE = "compatible_merge"
    VALUE_CONFLICT = "value_conflict"
    IDENTITY_CONFLICT = "identity_conflict"
    INVALID = "invalid"
    IGNORED = "ignored"


@dataclass(frozen=True)
class ReconRow:
    domain: str
    key: str
    classification: str
    field: str | None = None
    samir_value: Any = None
    julesh_value: Any = None
    notes: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReconReport:
    generated_at: str
    manifest: dict[str, Any]
    summary: dict[str, dict[str, int]] = field(default_factory=dict)
    rows: list[ReconRow] = field(default_factory=list)

    def add_rows(self, domain: str, rows: list[ReconRow]) -> None:
        self.rows.extend(rows)
        bucket = self.summary.setdefault(domain, {})
        for row in rows:
            bucket[row.classification] = bucket.get(row.classification, 0) + 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "manifest": self.manifest,
            "summary": self.summary,
            "rows": [r.as_dict() for r in self.rows],
        }
