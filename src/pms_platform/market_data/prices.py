"""Daily price CSV importer."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.ingestion.common import file_checksum
from pms_platform.market_data.common import (
    make_csv_source_key,
    parse_decimal,
    parse_iso_date,
    parse_optional_int,
    parse_required_iso_date,
    read_csv_rows,
)
from pms_platform.market_data.contracts import ADJUSTMENT_BASES, IDENTIFIER_TYPES
from pms_platform.market_data.identifiers import (
    IdentifierResolver,
    bootstrap_symbol_history_from_securities,
)
from pms_platform.market_data.normalize import (
    is_canonical_price_format,
    normalize_price_row,
    validate_price_columns,
)
from pms_platform.models import DailyPrice, ImportBatch


@dataclass(frozen=True)
class PriceImportResult:
    """Outcome of a daily price import."""

    inserted: int
    skipped: int
    unresolved: int
    invalid: int
    import_batch_id: int


@dataclass(frozen=True)
class ParsedPriceRow:
    """Validated CSV row ready for persistence."""

    identifier_type: str
    identifier: str
    trade_date: object
    close: Decimal
    adjusted_close: Decimal
    adjustment_basis: str
    volume: int | None
    currency: str
    source: str
    publication_date: object
    source_row: int


def import_daily_prices(session: Session, path: Path) -> PriceImportResult:
    """Import daily prices from the canonical or external package CSV contract."""
    rows, fieldnames = read_csv_rows(path)
    validate_price_columns(path, fieldnames)
    canonical = is_canonical_price_format(fieldnames)
    checksum = file_checksum(path)
    existing_batch = session.scalar(
        select(ImportBatch).where(
            ImportBatch.source_type == "daily_prices",
            ImportBatch.source_file == str(path),
            ImportBatch.source_checksum == checksum,
        )
    )
    if existing_batch is not None:
        count = len(session.scalars(select(DailyPrice)).all())
        return PriceImportResult(
            inserted=0,
            skipped=count,
            unresolved=0,
            invalid=0,
            import_batch_id=existing_batch.import_batch_id,
        )

    batch = ImportBatch(
        source_type="daily_prices",
        source_file=str(path),
        source_checksum=checksum,
        status="completed",
    )
    session.add(batch)
    session.flush()

    bootstrap_symbol_history_from_securities(
        session,
        source_file=str(path),
        import_batch_id=batch.import_batch_id,
    )

    resolver = IdentifierResolver(session)
    inserted = 0
    skipped = 0
    unresolved = 0
    invalid = 0
    seen_identity_keys: set[tuple[str | None, object, str]] = set()

    for row_number, raw_row in enumerate(rows, start=2):
        row = normalize_price_row(raw_row, canonical=canonical)
        source_key = make_csv_source_key(str(path), row_number)
        if (
            session.scalar(select(DailyPrice).where(DailyPrice.source_key == source_key))
            is not None
        ):
            skipped += 1
            continue

        try:
            parsed = _parse_price_row(row, row_number)
        except ValueError:
            invalid += 1
            continue

        if parsed.identifier_type not in IDENTIFIER_TYPES:
            invalid += 1
            continue
        if parsed.adjustment_basis not in ADJUSTMENT_BASES:
            invalid += 1
            continue
        if parsed.close <= 0 or parsed.adjusted_close <= 0:
            invalid += 1
            continue

        resolution = resolver.resolve(
            parsed.identifier_type,
            parsed.identifier,
            parsed.trade_date,  # type: ignore[arg-type]
        )
        security_id = resolution.security_id
        if security_id is None:
            unresolved += 1

        identity_key = (security_id, parsed.trade_date, parsed.source)
        if identity_key in seen_identity_keys:
            skipped += 1
            continue

        duplicate = session.scalar(
            select(DailyPrice).where(
                DailyPrice.security_id == security_id,
                DailyPrice.trade_date == parsed.trade_date,
                DailyPrice.source == parsed.source,
            )
        )
        if duplicate is not None:
            skipped += 1
            continue

        seen_identity_keys.add(identity_key)
        session.add(
            DailyPrice(
                security_id=security_id,
                identifier_type=parsed.identifier_type,
                identifier=parsed.identifier,
                trade_date=parsed.trade_date,  # type: ignore[arg-type]
                close=parsed.close,
                adjusted_close=parsed.adjusted_close,
                adjustment_basis=parsed.adjustment_basis,
                volume=parsed.volume,
                currency=parsed.currency,
                source=parsed.source,
                publication_date=parsed.publication_date,  # type: ignore[arg-type]
                source_file=str(path),
                source_row=row_number,
                source_key=source_key,
                import_batch_id=batch.import_batch_id,
            )
        )
        inserted += 1

    session.flush()
    return PriceImportResult(
        inserted=inserted,
        skipped=skipped,
        unresolved=unresolved,
        invalid=invalid,
        import_batch_id=batch.import_batch_id,
    )


def _parse_price_row(row: dict[str, str], row_number: int) -> ParsedPriceRow:
    return ParsedPriceRow(
        identifier_type=row["identifier_type"].strip().upper(),
        identifier=row["identifier"].strip(),
        trade_date=parse_required_iso_date(row["trade_date"], "trade_date"),
        close=parse_decimal(row["close"], "close"),
        adjusted_close=parse_decimal(row["adjusted_close"], "adjusted_close"),
        adjustment_basis=row["adjustment_basis"].strip().upper(),
        volume=parse_optional_int(row.get("volume")),
        currency=(row.get("currency") or "INR").strip().upper(),
        source=row["source"].strip(),
        publication_date=parse_iso_date(row.get("publication_date"), "publication_date"),
        source_row=row_number,
    )
