"""Validation tests."""

from datetime import date

from helpers import add_transaction
from pms_platform.ingestion.validators import (
    ValidationSeverity,
    validate_quantity_sign,
    validate_transactions,
)
from pms_platform.models.enums import EventType


def test_validate_quantity_sign_buy_sell() -> None:
    """Buy requires positive quantity; sell requires negative quantity."""
    assert validate_quantity_sign(EventType.BUY.value, 100) is None
    assert validate_quantity_sign(EventType.SELL.value, -50) is None
    assert validate_quantity_sign(EventType.BUY.value, -1) is not None
    assert validate_quantity_sign(EventType.SELL.value, 10) is not None


def test_validate_oversell(session, import_batch, sample_security) -> None:
    """Overselling produces a validation error."""
    add_transaction(
        session, import_batch, sample_security.security_id, date(2020, 1, 1), EventType.BUY, 100, 1
    )
    add_transaction(
        session,
        import_batch,
        sample_security.security_id,
        date(2020, 2, 1),
        EventType.SELL,
        -150,
        2,
    )
    session.commit()

    issues = validate_transactions(session)
    assert any(issue.code == "NEGATIVE_HOLDING" for issue in issues)


def test_validate_missing_price_warning(session, import_batch, sample_security) -> None:
    """Missing trade price on buy/sell rows produces a warning."""
    add_transaction(
        session, import_batch, sample_security.security_id, date(2020, 1, 1), EventType.BUY, 100, 1
    )
    session.commit()

    issues = validate_transactions(session)
    warnings = [issue for issue in issues if issue.code == "MISSING_PRICE"]
    assert warnings
    assert warnings[0].severity == ValidationSeverity.WARNING
