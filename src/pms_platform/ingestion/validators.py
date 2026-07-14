"""Import validation rules."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.models import LiquidTransaction, Security, Transaction
from pms_platform.models.enums import EventType, ValidationSeverity


@dataclass(frozen=True)
class ValidationIssue:
    """Single validation finding."""

    severity: ValidationSeverity
    code: str
    message: str
    security_id: str | None = None
    source_key: str | None = None
    event_date: date | None = None


def validate_quantity_sign(event_type: str, quantity: int) -> ValidationIssue | None:
    """Validate quantity sign against event type."""
    event = EventType.from_workbook(event_type)
    positive_expected = {
        EventType.BUY,
        EventType.BONUS,
        EventType.SPLIT,
        EventType.RIGHTS,
        EventType.DEMERGER,
        EventType.MERGER,
        EventType.CONVERSION,
    }
    if event in positive_expected and quantity <= 0:
        return ValidationIssue(
            severity=ValidationSeverity.ERROR,
            code="INVALID_QUANTITY_SIGN",
            message=f"{event.value} must have positive quantity, got {quantity}",
        )
    if event == EventType.SELL and quantity >= 0:
        return ValidationIssue(
            severity=ValidationSeverity.ERROR,
            code="INVALID_QUANTITY_SIGN",
            message=f"Sell must have negative quantity, got {quantity}",
        )
    return None


def validate_securities(session: Session) -> list[ValidationIssue]:
    """Validate security master contents."""
    issues: list[ValidationIssue] = []
    securities = list(session.scalars(select(Security)).all())
    if len(securities) != 75:
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="SECURITY_COUNT_MISMATCH",
                message=f"Expected 75 securities, found {len(securities)}",
            )
        )

    liquid_names = {"LiquidCase", "Liquid Case", "LiquidBees"}
    for security in securities:
        if security.portfolio_name in liquid_names:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="LIQUID_IN_SECURITY_MASTER",
                    message=f"Liquid holding {security.portfolio_name!r} must not be in Security Master",
                    security_id=security.security_id,
                )
            )
    return issues


def validate_transactions(session: Session) -> list[ValidationIssue]:
    """Validate equity and liquid transaction rows."""
    issues: list[ValidationIssue] = []
    transactions = list(
        session.scalars(
            select(Transaction).order_by(
                Transaction.security_id,
                Transaction.event_date,
                Transaction.source_row,
            )
        )
    )
    liquid_transactions = list(session.scalars(select(LiquidTransaction)))

    for txn in transactions:
        sign_issue = validate_quantity_sign(txn.event_type, txn.quantity)
        if sign_issue is not None:
            issues.append(
                ValidationIssue(
                    severity=sign_issue.severity,
                    code=sign_issue.code,
                    message=sign_issue.message,
                    security_id=txn.security_id,
                    source_key=txn.source_key,
                    event_date=txn.event_date,
                )
            )

    running: dict[str, int] = {}
    for txn in transactions:
        before = running.get(txn.security_id, 0)
        after = before + txn.quantity
        if after < 0:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="NEGATIVE_HOLDING",
                    message=(
                        f"Transaction would create negative holding for {txn.security_id}: "
                        f"{before} + {txn.quantity} = {after}"
                    ),
                    security_id=txn.security_id,
                    source_key=txn.source_key,
                    event_date=txn.event_date,
                )
            )
        running[txn.security_id] = after

    for liquid_txn in liquid_transactions:
        sign_issue = validate_quantity_sign(liquid_txn.event_type, liquid_txn.quantity)
        if sign_issue is not None:
            issues.append(
                ValidationIssue(
                    severity=sign_issue.severity,
                    code=sign_issue.code,
                    message=sign_issue.message,
                    source_key=liquid_txn.source_key,
                    event_date=liquid_txn.event_date,
                )
            )

    for txn in transactions:
        if txn.price is None and txn.event_type in {EventType.BUY.value, EventType.SELL.value}:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    code="MISSING_PRICE",
                    message="Trade price unavailable for buy/sell row",
                    security_id=txn.security_id,
                    source_key=txn.source_key,
                    event_date=txn.event_date,
                )
            )

    return issues


def validate_imported_data(session: Session) -> list[ValidationIssue]:
    """Run validation checks across imported securities and transactions."""
    issues = validate_securities(session)
    issues.extend(validate_transactions(session))
    return issues
