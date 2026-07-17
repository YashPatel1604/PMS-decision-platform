"""Benchmark TRI CSV importer."""

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
from pms_platform.market_data.normalize import (
    is_canonical_benchmark_format,
    normalize_benchmark_row,
    validate_benchmark_columns,
)
from pms_platform.models import BenchmarkTri, ImportBatch


@dataclass(frozen=True)
class BenchmarkImportResult:
    """Outcome of a benchmark TRI import."""

    inserted: int
    skipped: int
    invalid: int
    import_batch_id: int


def import_benchmark_tri(session: Session, path: Path) -> BenchmarkImportResult:
    """Import benchmark TRI levels from the canonical or external package CSV contract."""
    rows, fieldnames = read_csv_rows(path)
    validate_benchmark_columns(path, fieldnames)
    canonical = is_canonical_benchmark_format(fieldnames)
    checksum = file_checksum(path)
    existing_batch = session.scalar(
        select(ImportBatch).where(
            ImportBatch.source_type == "benchmark_tri",
            ImportBatch.source_file == str(path),
            ImportBatch.source_checksum == checksum,
        )
    )
    if existing_batch is not None:
        count = len(session.scalars(select(BenchmarkTri)).all())
        return BenchmarkImportResult(
            inserted=0,
            skipped=count,
            invalid=0,
            import_batch_id=existing_batch.import_batch_id,
        )

    batch = ImportBatch(
        source_type="benchmark_tri",
        source_file=str(path),
        source_checksum=checksum,
        status="completed",
    )
    session.add(batch)
    session.flush()

    inserted = 0
    skipped = 0
    invalid = 0
    seen_identity_keys: set[tuple[str, object, str]] = set()

    for row_number, raw_row in enumerate(rows, start=2):
        row = normalize_benchmark_row(raw_row, canonical=canonical)
        source_key = make_csv_source_key(str(path), row_number)
        if (
            session.scalar(select(BenchmarkTri).where(BenchmarkTri.source_key == source_key))
            is not None
        ):
            skipped += 1
            continue

        try:
            benchmark_code = row["benchmark_code"].strip().upper()
            trade_date = parse_required_iso_date(row["trade_date"], "trade_date")
            tri_level = parse_decimal(row["tri_level"], "tri_level")
            source = row["source"].strip()
            publication_date = parse_iso_date(row.get("publication_date"), "publication_date")
            methodology_version = row.get("methodology_version", "").strip() or None
        except ValueError:
            invalid += 1
            continue

        if tri_level <= 0:
            invalid += 1
            continue

        identity_key = (benchmark_code, trade_date, source)
        if identity_key in seen_identity_keys:
            skipped += 1
            continue

        duplicate = session.scalar(
            select(BenchmarkTri).where(
                BenchmarkTri.benchmark_code == benchmark_code,
                BenchmarkTri.trade_date == trade_date,
                BenchmarkTri.source == source,
            )
        )
        if duplicate is not None:
            skipped += 1
            continue

        seen_identity_keys.add(identity_key)
        session.add(
            BenchmarkTri(
                benchmark_code=benchmark_code,
                trade_date=trade_date,
                tri_level=tri_level,
                source=source,
                publication_date=publication_date,
                methodology_version=methodology_version,
                source_file=str(path),
                source_row=row_number,
                source_key=source_key,
                import_batch_id=batch.import_batch_id,
            )
        )
        inserted += 1

    session.flush()
    return BenchmarkImportResult(
        inserted=inserted,
        skipped=skipped,
        invalid=invalid,
        import_batch_id=batch.import_batch_id,
    )
