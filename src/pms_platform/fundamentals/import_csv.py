"""Quarterly fundamentals CSV importer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.fundamentals.catalog import (
    CONTRACT_VERSION,
    FUNDAMENTALS_PROVIDERS,
    QUARTERLY_FUNDAMENTALS_COLUMNS,
)
from pms_platform.ingestion.common import file_checksum
from pms_platform.market_data.common import (
    make_csv_source_key,
    parse_required_iso_date,
    read_csv_rows,
    validate_required_columns,
)
from pms_platform.market_data.contracts import IDENTIFIER_TYPES
from pms_platform.market_data.identifiers import IdentifierResolver
from pms_platform.models import ImportBatch
from pms_platform.models.company_fundamentals_quarterly import CompanyFundamentalsQuarterly


@dataclass(frozen=True)
class FundamentalsImportResult:
    """Outcome of a quarterly fundamentals CSV import."""

    inserted: int
    updated: int
    skipped: int
    invalid: int
    import_batch_id: int


def parse_optional_decimal(value: object, field_name: str) -> Decimal | None:
    """Parse an optional decimal from a CSV cell."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value).strip())
    except Exception as exc:
        msg = f"Invalid {field_name}: {value!r}"
        raise ValueError(msg) from exc


def import_quarterly_fundamentals(
    session: Session,
    path: Path,
    *,
    provider: str = "manual",
) -> FundamentalsImportResult:
    """Import quarterly fundamentals from the canonical CSV contract."""
    rows, fieldnames = read_csv_rows(path)
    validate_required_columns(path, QUARTERLY_FUNDAMENTALS_COLUMNS)
    checksum = file_checksum(path)

    existing_batch = session.scalar(
        select(ImportBatch).where(
            ImportBatch.source_type == "quarterly_fundamentals",
            ImportBatch.source_file == str(path),
            ImportBatch.source_checksum == checksum,
        )
    )
    if existing_batch is not None:
        count = len(session.scalars(select(CompanyFundamentalsQuarterly)).all())
        return FundamentalsImportResult(
            inserted=0,
            updated=0,
            skipped=count,
            invalid=0,
            import_batch_id=existing_batch.import_batch_id,
        )

    batch = ImportBatch(
        source_type="quarterly_fundamentals",
        source_file=str(path),
        source_checksum=checksum,
        status="completed",
    )
    session.add(batch)
    session.flush()

    resolver = IdentifierResolver(session)
    inserted = 0
    updated = 0
    skipped = 0
    invalid = 0

    for row_number, raw_row in enumerate(rows, start=2):
        source_key = make_csv_source_key(str(path), row_number)
        try:
            contract_version = raw_row.get("contract_version", CONTRACT_VERSION).strip()
            identifier_type = raw_row["identifier_type"].strip().upper()
            identifier = raw_row["identifier"].strip()
            fiscal_year = int(raw_row["fiscal_year"].strip())
            fiscal_quarter = raw_row["fiscal_quarter"].strip().upper()
            period_end_date = parse_required_iso_date(raw_row["period_end_date"], "period_end_date")
            sales = parse_optional_decimal(raw_row.get("sales"), "sales")
            ebitda = parse_optional_decimal(raw_row.get("ebitda"), "ebitda")
            ebit = parse_optional_decimal(raw_row.get("ebit"), "ebit")
            pat = parse_optional_decimal(raw_row.get("pat"), "pat")
            opm = parse_optional_decimal(raw_row.get("opm"), "opm")
            npm = parse_optional_decimal(raw_row.get("npm"), "npm")
            source = raw_row["source"].strip()
            row_provider = raw_row.get("provider", provider).strip().lower() or provider
            retrieved_raw = raw_row.get("retrieved_at", "").strip()
            retrieved_at = (
                datetime.fromisoformat(retrieved_raw.replace("Z", "+00:00"))
                if retrieved_raw
                else datetime.now(timezone.utc)
            )
        except (ValueError, KeyError):
            invalid += 1
            continue

        if identifier_type not in IDENTIFIER_TYPES:
            invalid += 1
            continue
        if row_provider not in FUNDAMENTALS_PROVIDERS:
            invalid += 1
            continue
        if contract_version != CONTRACT_VERSION:
            invalid += 1
            continue

        resolution = resolver.resolve(identifier_type, identifier, period_end_date)
        security_id = resolution.security_id if resolution.status == "RESOLVED" else None

        existing = session.scalar(
            select(CompanyFundamentalsQuarterly).where(
                CompanyFundamentalsQuarterly.identifier_type == identifier_type,
                CompanyFundamentalsQuarterly.identifier == identifier,
                CompanyFundamentalsQuarterly.period_end_date == period_end_date,
                CompanyFundamentalsQuarterly.source == source,
            )
        )
        if existing is not None:
            existing.security_id = security_id
            existing.fiscal_year = fiscal_year
            existing.fiscal_quarter = fiscal_quarter
            existing.sales = sales
            existing.ebitda = ebitda
            existing.ebit = ebit
            existing.pat = pat
            existing.opm = opm
            existing.npm = npm
            existing.provider = row_provider
            existing.contract_version = contract_version
            existing.retrieved_at = retrieved_at
            existing.source_file = str(path)
            existing.source_row = row_number
            existing.source_key = source_key
            existing.import_batch_id = batch.import_batch_id
            updated += 1
            continue

        duplicate_source_key = session.scalar(
            select(CompanyFundamentalsQuarterly).where(
                CompanyFundamentalsQuarterly.source_key == source_key
            )
        )
        if duplicate_source_key is not None:
            skipped += 1
            continue

        session.add(
            CompanyFundamentalsQuarterly(
                identifier_type=identifier_type,
                identifier=identifier,
                security_id=security_id,
                fiscal_year=fiscal_year,
                fiscal_quarter=fiscal_quarter,
                period_end_date=period_end_date,
                sales=sales,
                ebitda=ebitda,
                ebit=ebit,
                pat=pat,
                opm=opm,
                npm=npm,
                source=source,
                provider=row_provider,
                contract_version=contract_version,
                retrieved_at=retrieved_at,
                source_file=str(path),
                source_row=row_number,
                source_key=source_key,
                import_batch_id=batch.import_batch_id,
            )
        )
        inserted += 1

    session.flush()
    return FundamentalsImportResult(
        inserted=inserted,
        updated=updated,
        skipped=skipped,
        invalid=invalid,
        import_batch_id=batch.import_batch_id,
    )
