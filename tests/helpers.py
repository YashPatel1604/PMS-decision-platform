"""Shared test helpers."""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from pms_platform.models import ImportBatch, Transaction
from pms_platform.models.enums import EventType


def add_transaction(
    session: Session,
    import_batch: ImportBatch,
    security_id: str,
    event_date: date,
    event_type: EventType,
    quantity: int,
    source_row: int,
    price: Decimal | None = None,
) -> Transaction:
    """Insert a test transaction row."""
    source_key = f"test.xlsx|Sheet1|{source_row}"
    txn = Transaction(
        security_id=security_id,
        event_date=event_date,
        event_type=event_type.value,
        quantity=quantity,
        price=price,
        source_file="test.xlsx",
        source_sheet="Sheet1",
        source_row=source_row,
        source_note="test fixture",
        source_key=source_key,
        import_batch_id=import_batch.import_batch_id,
    )
    session.add(txn)
    session.flush()
    return txn
