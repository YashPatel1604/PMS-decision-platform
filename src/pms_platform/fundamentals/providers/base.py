"""Fundamentals provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class ProviderImportResult:
    """Outcome of a fundamentals provider fetch/import."""

    inserted: int
    updated: int
    skipped: int
    invalid: int
    import_batch_id: int | None


class FundamentalsProvider(ABC):
    """Fetch or load quarterly fundamentals into the database."""

    name: str

    @abstractmethod
    def import_data(self, session: Session, *, path: Path | None = None) -> ProviderImportResult:
        """Load fundamentals from the provider source."""
