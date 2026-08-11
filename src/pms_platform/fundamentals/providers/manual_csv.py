"""Manual CSV and screener-export fundamentals provider."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from pms_platform.fundamentals.import_csv import FundamentalsImportResult, import_quarterly_fundamentals
from pms_platform.fundamentals.providers.base import FundamentalsProvider, ProviderImportResult


class ManualCsvProvider(FundamentalsProvider):
    """Import from the canonical quarterly_fundamentals.csv contract."""

    name = "manual"

    def import_data(self, session: Session, *, path: Path | None = None) -> ProviderImportResult:
        if path is None:
            msg = "ManualCsvProvider requires a CSV path"
            raise ValueError(msg)
        result = import_quarterly_fundamentals(session, path, provider=self.name)
        return _to_provider_result(result)


class ScreenerExportProvider(FundamentalsProvider):
    """Same CSV contract as manual; tags rows with provider=screener."""

    name = "screener"

    def import_data(self, session: Session, *, path: Path | None = None) -> ProviderImportResult:
        if path is None:
            msg = "ScreenerExportProvider requires a CSV path"
            raise ValueError(msg)
        result = import_quarterly_fundamentals(session, path, provider=self.name)
        return _to_provider_result(result)


def _to_provider_result(result: FundamentalsImportResult) -> ProviderImportResult:
    return ProviderImportResult(
        inserted=result.inserted,
        updated=result.updated,
        skipped=result.skipped,
        invalid=result.invalid,
        import_batch_id=result.import_batch_id,
    )
