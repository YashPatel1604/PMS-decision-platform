"""Running quantity tests."""

from datetime import date

from helpers import add_transaction
from pms_platform.ingestion.validators import validate_transactions
from pms_platform.models.enums import EventType


def test_running_quantity_after_split(session, import_batch, sample_security) -> None:
    """Running quantity reflects split adjustments."""
    add_transaction(session, import_batch, sample_security.security_id, date(2025, 1, 1), EventType.BUY, 1065, 1)
    add_transaction(session, import_batch, sample_security.security_id, date(2026, 6, 5), EventType.SPLIT, 9585, 2)
    add_transaction(
        session, import_batch, sample_security.security_id, date(2026, 6, 22), EventType.SELL, -3094, 3
    )
    session.commit()

    issues = validate_transactions(session)
    negative = [issue for issue in issues if issue.code == "NEGATIVE_HOLDING"]
    assert not negative
