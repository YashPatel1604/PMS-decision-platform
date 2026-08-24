"""Shared result type for fundamentals imports."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderImportResult:
    """Outcome of a fundamentals provider fetch/import."""

    inserted: int
    updated: int
    skipped: int
    invalid: int
    import_batch_id: int | None
