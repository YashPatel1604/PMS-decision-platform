"""Transaction Master Excel importer."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import openpyxl
from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.ingestion.common import (
    file_checksum,
    is_liquid_holding,
    make_source_key,
    parse_workbook_date,
    to_decimal,
    to_int_quantity,
)
from pms_platform.models import ImportBatch, LiquidTransaction, Security, Transaction
from pms_platform.models.enums import EventType


@dataclass(frozen=True)
class ParsedTransactionRow:
    """Normalized transaction row from the workbook."""

    portfolio_name: str
    event_date: date
    event_type: EventType
    quantity: int
    price: Decimal | None
    amount: Decimal | None
    source_file: str
    source_sheet: str
    source_row: int
    source_note: str | None


@dataclass(frozen=True)
class TransactionImportResult:
    """Outcome of a transaction master import."""

    equity_inserted: int
    equity_skipped: int
    liquid_inserted: int
    liquid_skipped: int
    summary_rows_skipped: int
    import_batch_id: int


def parse_transaction_workbook(
    path: Path, sheet_name: str = "Sheet1"
) -> tuple[list[ParsedTransactionRow], int]:
    """Parse transaction rows, skipping per-stock total rows."""
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    worksheet = workbook[sheet_name]
    rows = list(worksheet.iter_rows(values_only=True))
    workbook.close()

    current_stock: str | None = None
    parsed: list[ParsedTransactionRow] = []
    summary_rows_skipped = 0

    for row_number, row in enumerate(rows[1:], start=2):
        _, stock, event_date, event_label, quantity, price, amount, source_note = (
            row + (None,) * 8
        )[:8]

        if stock is not None and str(stock).strip():
            current_stock = str(stock).strip()

        if event_date is None and event_label is None and quantity is not None:
            summary_rows_skipped += 1
            continue

        if current_stock is None or event_date is None or event_label is None or quantity is None:
            continue

        parsed.append(
            ParsedTransactionRow(
                portfolio_name=current_stock,
                event_date=parse_workbook_date(event_date),
                event_type=EventType.from_workbook(str(event_label)),
                quantity=to_int_quantity(quantity),
                price=to_decimal(price),
                amount=to_decimal(amount),
                source_file=str(path),
                source_sheet=sheet_name,
                source_row=row_number,
                source_note=str(source_note).strip() if source_note else None,
            )
        )

    return parsed, summary_rows_skipped


def import_transaction_master(session: Session, path: Path) -> TransactionImportResult:
    """Import equity and liquid transactions idempotently."""
    checksum = file_checksum(path)
    existing_batch = session.scalar(
        select(ImportBatch).where(
            ImportBatch.source_type == "transactions",
            ImportBatch.source_file == str(path),
            ImportBatch.source_checksum == checksum,
        )
    )
    if existing_batch is not None:
        equity_count = len(
            session.scalars(
                select(Transaction).where(
                    Transaction.import_batch_id == existing_batch.import_batch_id
                )
            ).all()
        )
        liquid_count = len(
            session.scalars(
                select(LiquidTransaction).where(
                    LiquidTransaction.import_batch_id == existing_batch.import_batch_id
                )
            ).all()
        )
        return TransactionImportResult(
            equity_inserted=0,
            equity_skipped=equity_count,
            liquid_inserted=0,
            liquid_skipped=liquid_count,
            summary_rows_skipped=0,
            import_batch_id=existing_batch.import_batch_id,
        )

    batch = ImportBatch(
        source_type="transactions",
        source_file=str(path),
        source_checksum=checksum,
        status="completed",
    )
    session.add(batch)
    session.flush()

    parsed_rows, summary_rows_skipped = parse_transaction_workbook(path)
    portfolio_to_security = {
        security.portfolio_name: security.security_id
        for security in session.scalars(select(Security)).all()
    }

    equity_inserted = 0
    equity_skipped = 0
    liquid_inserted = 0
    liquid_skipped = 0

    for row in parsed_rows:
        source_key = make_source_key(row.source_file, row.source_sheet, row.source_row)
        if is_liquid_holding(row.portfolio_name):
            if session.scalar(
                select(LiquidTransaction).where(LiquidTransaction.source_key == source_key)
            ):
                liquid_skipped += 1
                continue
            session.add(
                LiquidTransaction(
                    event_date=row.event_date,
                    event_type=row.event_type.value,
                    quantity=row.quantity,
                    price=row.price,
                    amount=row.amount,
                    source_file=row.source_file,
                    source_sheet=row.source_sheet,
                    source_row=row.source_row,
                    source_note=row.source_note,
                    source_key=source_key,
                    import_batch_id=batch.import_batch_id,
                )
            )
            liquid_inserted += 1
            continue

        security_id = portfolio_to_security.get(row.portfolio_name)
        if security_id is None:
            msg = f"Unknown security portfolio name: {row.portfolio_name!r} at row {row.source_row}"
            raise ValueError(msg)

        if session.scalar(select(Transaction).where(Transaction.source_key == source_key)):
            equity_skipped += 1
            continue

        session.add(
            Transaction(
                security_id=security_id,
                event_date=row.event_date,
                event_type=row.event_type.value,
                quantity=row.quantity,
                price=row.price,
                amount=row.amount,
                source_file=row.source_file,
                source_sheet=row.source_sheet,
                source_row=row.source_row,
                source_note=row.source_note,
                source_key=source_key,
                import_batch_id=batch.import_batch_id,
            )
        )
        equity_inserted += 1

    session.flush()
    return TransactionImportResult(
        equity_inserted=equity_inserted,
        equity_skipped=equity_skipped,
        liquid_inserted=liquid_inserted,
        liquid_skipped=liquid_skipped,
        summary_rows_skipped=summary_rows_skipped,
        import_batch_id=batch.import_batch_id,
    )
