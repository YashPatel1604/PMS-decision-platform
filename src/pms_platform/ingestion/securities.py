"""Security Master Excel importer."""

from dataclasses import dataclass
from pathlib import Path

import openpyxl
from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.ingestion.common import file_checksum, make_source_key
from pms_platform.models import ImportBatch, Security


@dataclass(frozen=True)
class SecurityImportResult:
    """Outcome of a security master import."""

    inserted: int
    updated: int
    skipped: int
    import_batch_id: int


def import_security_master(session: Session, path: Path) -> SecurityImportResult:
    """Import or update securities from the Security Master workbook."""
    checksum = file_checksum(path)
    existing_batch = session.scalar(
        select(ImportBatch).where(
            ImportBatch.source_type == "securities",
            ImportBatch.source_file == str(path),
            ImportBatch.source_checksum == checksum,
        )
    )
    if existing_batch is not None:
        securities_count = len(session.scalars(select(Security)).all())
        return SecurityImportResult(
            inserted=0,
            updated=0,
            skipped=securities_count,
            import_batch_id=existing_batch.import_batch_id,
        )

    batch = ImportBatch(
        source_type="securities",
        source_file=str(path),
        source_checksum=checksum,
        status="completed",
    )
    session.add(batch)
    session.flush()

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    worksheet = workbook["Security Master"]
    rows = list(worksheet.iter_rows(values_only=True))
    workbook.close()

    inserted = 0
    updated = 0
    for row_number, row in enumerate(rows[1:], start=2):
        if not any(cell is not None and str(cell).strip() for cell in row):
            continue

        (
            security_id,
            portfolio_name,
            canonical_name,
            current_nse_symbol,
            historical_nse_symbol,
            bse_code,
            isin,
            status,
            corporate_history,
            sector,
            industry,
            verification_status,
        ) = (row + (None,) * 12)[:12]

        if security_id is None or portfolio_name is None:
            continue

        bse_text = str(int(bse_code)) if isinstance(bse_code, (int, float)) else (
            str(bse_code).strip() if bse_code is not None else None
        )

        existing = session.get(Security, str(security_id).strip())
        payload = {
            "security_id": str(security_id).strip(),
            "portfolio_name": str(portfolio_name).strip(),
            "canonical_name": str(canonical_name).strip() if canonical_name else None,
            "current_nse_symbol": str(current_nse_symbol).strip() if current_nse_symbol else None,
            "historical_nse_symbol": str(historical_nse_symbol).strip() if historical_nse_symbol else None,
            "bse_code": bse_text,
            "isin": str(isin).strip() if isin else None,
            "status": str(status).strip() if status else None,
            "corporate_history": str(corporate_history).strip() if corporate_history else None,
            "sector": str(sector).strip() if sector else None,
            "industry": str(industry).strip() if industry else None,
            "verification_status": str(verification_status).strip() if verification_status else None,
            "import_batch_id": batch.import_batch_id,
        }

        if existing is None:
            session.add(Security(**payload))
            inserted += 1
        else:
            for key, value in payload.items():
                if key != "security_id":
                    setattr(existing, key, value)
            updated += 1

        _ = make_source_key(str(path), "Security Master", row_number)

    session.flush()
    return SecurityImportResult(
        inserted=inserted,
        updated=updated,
        skipped=0,
        import_batch_id=batch.import_batch_id,
    )
