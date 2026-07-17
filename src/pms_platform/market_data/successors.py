"""Security successor CSV importer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.ingestion.common import file_checksum
from pms_platform.market_data.common import (
    make_csv_source_key,
    parse_required_iso_date,
    read_csv_rows,
)
from pms_platform.market_data.normalize import (
    is_canonical_successor_format,
    normalize_successor_row,
    validate_successor_columns,
)
from pms_platform.models import ImportBatch, Security, SecuritySuccessor


@dataclass(frozen=True)
class SuccessorImportResult:
    """Outcome of a security successor import."""

    inserted: int
    skipped: int
    invalid: int
    import_batch_id: int


def import_security_successors(session: Session, path: Path) -> SuccessorImportResult:
    """Import successor mappings from canonical or external package CSV."""
    rows, fieldnames = read_csv_rows(path)
    validate_successor_columns(path, fieldnames)
    canonical = is_canonical_successor_format(fieldnames)
    checksum = file_checksum(path)
    existing_batch = session.scalar(
        select(ImportBatch).where(
            ImportBatch.source_type == "security_successors",
            ImportBatch.source_file == str(path),
            ImportBatch.source_checksum == checksum,
        )
    )
    if existing_batch is not None:
        count = len(session.scalars(select(SecuritySuccessor)).all())
        return SuccessorImportResult(
            inserted=0,
            skipped=count,
            invalid=0,
            import_batch_id=existing_batch.import_batch_id,
        )

    batch = ImportBatch(
        source_type="security_successors",
        source_file=str(path),
        source_checksum=checksum,
        status="completed",
    )
    session.add(batch)
    session.flush()

    known_security_ids = set(session.scalars(select(Security.security_id)).all())
    inserted = 0
    skipped = 0
    invalid = 0

    for row_number, raw_row in enumerate(rows, start=2):
        normalized = normalize_successor_row(raw_row, canonical=canonical)
        if normalized is None:
            invalid += 1
            continue

        source_key = make_csv_source_key(str(path), row_number)
        if (
            session.scalar(
                select(SecuritySuccessor).where(SecuritySuccessor.source_key == source_key)
            )
            is not None
        ):
            skipped += 1
            continue

        try:
            predecessor_security_id = normalized["predecessor_security_id"].strip()
            successor_security_id = normalized["successor_security_id"].strip()
            effective_date = parse_required_iso_date(
                normalized["effective_date"], "effective_date"
            )
            action_type = normalized["action_type"].strip().upper()
            confirmed_text = str(normalized.get("confirmed", "")).strip().lower()
            confirmed = confirmed_text in {"1", "true", "yes", "y"}
        except (ValueError, KeyError):
            invalid += 1
            continue

        if (
            predecessor_security_id not in known_security_ids
            or successor_security_id not in known_security_ids
        ):
            invalid += 1
            continue

        duplicate = session.scalar(
            select(SecuritySuccessor).where(
                SecuritySuccessor.predecessor_security_id == predecessor_security_id,
                SecuritySuccessor.successor_security_id == successor_security_id,
                SecuritySuccessor.effective_date == effective_date,
                SecuritySuccessor.action_type == action_type,
            )
        )
        if duplicate is not None:
            skipped += 1
            continue

        session.add(
            SecuritySuccessor(
                predecessor_security_id=predecessor_security_id,
                successor_security_id=successor_security_id,
                effective_date=effective_date,
                action_type=action_type,
                confirmed=confirmed,
                source_file=str(path),
                source_row=row_number,
                source_key=source_key,
                import_batch_id=batch.import_batch_id,
            )
        )
        inserted += 1

    session.flush()
    return SuccessorImportResult(
        inserted=inserted,
        skipped=skipped,
        invalid=invalid,
        import_batch_id=batch.import_batch_id,
    )
