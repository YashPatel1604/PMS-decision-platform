"""Dividend CSV importer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.ingestion.common import file_checksum
from pms_platform.market_data.common import (
    make_csv_source_key,
    parse_decimal,
    parse_iso_date,
    parse_required_iso_date,
    read_csv_rows,
)
from pms_platform.market_data.contracts import IDENTIFIER_TYPES
from pms_platform.market_data.identifiers import IdentifierResolver
from pms_platform.market_data.normalize import (
    is_canonical_dividend_format,
    normalize_dividend_row,
    validate_dividend_columns,
)
from pms_platform.models import Dividend, ImportBatch


@dataclass(frozen=True)
class DividendImportResult:
    """Outcome of a dividend import."""

    inserted: int
    skipped: int
    unresolved: int
    invalid: int
    import_batch_id: int


def import_dividends(session: Session, path: Path) -> DividendImportResult:
    """Import dividend events from the canonical or external package CSV contract."""
    rows, fieldnames = read_csv_rows(path)
    validate_dividend_columns(path, fieldnames)
    canonical = is_canonical_dividend_format(fieldnames)
    checksum = file_checksum(path)
    existing_batch = session.scalar(
        select(ImportBatch).where(
            ImportBatch.source_type == "dividends",
            ImportBatch.source_file == str(path),
            ImportBatch.source_checksum == checksum,
        )
    )
    if existing_batch is not None:
        count = len(session.scalars(select(Dividend)).all())
        return DividendImportResult(
            inserted=0,
            skipped=count,
            unresolved=0,
            invalid=0,
            import_batch_id=existing_batch.import_batch_id,
        )

    batch = ImportBatch(
        source_type="dividends",
        source_file=str(path),
        source_checksum=checksum,
        status="completed",
    )
    session.add(batch)
    session.flush()

    resolver = IdentifierResolver(session)
    inserted = 0
    skipped = 0
    unresolved = 0
    invalid = 0
    seen_identity_keys: set[tuple[str | None, object, str]] = set()

    for row_number, raw_row in enumerate(rows, start=2):
        row = normalize_dividend_row(raw_row, canonical=canonical)
        source_key = make_csv_source_key(str(path), row_number)
        if session.scalar(select(Dividend).where(Dividend.source_key == source_key)) is not None:
            skipped += 1
            continue

        try:
            identifier_type = row["identifier_type"].strip().upper()
            identifier = row["identifier"].strip()
            ex_date = parse_required_iso_date(row["ex_date"], "ex_date")
            dividend_per_share = parse_decimal(row["dividend_per_share"], "dividend_per_share")
            currency = (row.get("currency") or "INR").strip().upper()
            source = row["source"].strip()
            publication_date = parse_iso_date(row.get("publication_date"), "publication_date")
            record_date = parse_iso_date(row.get("record_date"), "record_date")
            payment_date = parse_iso_date(row.get("payment_date"), "payment_date")
        except ValueError:
            invalid += 1
            continue

        if identifier_type not in IDENTIFIER_TYPES or dividend_per_share <= 0:
            invalid += 1
            continue

        resolution = resolver.resolve(identifier_type, identifier, ex_date)
        security_id = resolution.security_id
        if security_id is None:
            unresolved += 1

        identity_key = (security_id, ex_date, source)
        if identity_key in seen_identity_keys:
            skipped += 1
            continue

        duplicate = session.scalar(
            select(Dividend).where(
                Dividend.security_id == security_id,
                Dividend.ex_date == ex_date,
                Dividend.source == source,
            )
        )
        if duplicate is not None:
            skipped += 1
            continue

        seen_identity_keys.add(identity_key)
        session.add(
            Dividend(
                security_id=security_id,
                identifier_type=identifier_type,
                identifier=identifier,
                ex_date=ex_date,
                record_date=record_date,
                payment_date=payment_date,
                dividend_per_share=dividend_per_share,
                currency=currency,
                source=source,
                publication_date=publication_date,
                source_file=str(path),
                source_row=row_number,
                source_key=source_key,
                import_batch_id=batch.import_batch_id,
            )
        )
        inserted += 1

    session.flush()
    return DividendImportResult(
        inserted=inserted,
        skipped=skipped,
        unresolved=unresolved,
        invalid=invalid,
        import_batch_id=batch.import_batch_id,
    )
