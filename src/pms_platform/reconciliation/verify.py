"""Post-import verification for migration rehearsal."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pms_platform.models.charts_range import ChartsRangeRow
from pms_platform.models.client_book_settings import ClientBookSettings
from pms_platform.models.client_position import ClientPosition
from pms_platform.models.nse_bhav import PivotPortfolioSymbol
from pms_platform.models.security import Security
from pms_platform.models.watchlist import WatchlistMember
from pms_platform.reconciliation.copy_bhav import bhav_bar_count
from pms_platform.reconciliation.import_bundle import load_migration_bundle


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


@dataclass
class RehearsalVerification:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.checks)

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in self.checks],
        }


def _bundle_domain_count(bundle: dict[str, Any], domain: str) -> int:
    return len((bundle.get("domains") or {}).get(domain) or {})


def _db_count(session: Session, model) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _qty_sum_by_book(session: Session) -> dict[str, Decimal]:
    rows = session.execute(
        select(ClientPosition.book, func.sum(ClientPosition.qty)).group_by(ClientPosition.book)
    ).all()
    return {book: Decimal(str(total or 0)) for book, total in rows}


def _bundle_qty_sum_by_book(bundle: dict[str, Any]) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    for row in (bundle.get("domains") or {}).get("client_positions", {}).values():
        book = row["book"]
        out[book] = out.get(book, Decimal("0")) + Decimal(str(row["qty"]))
    return out


def _bundle_bank_balances(bundle: dict[str, Any]) -> dict[str, Decimal | None]:
    out: dict[str, Decimal | None] = {}
    for book, row in (bundle.get("domains") or {}).get("client_book_settings", {}).items():
        book_key = row.get("book", book)
        val = row.get("bank_balance")
        out[book_key] = Decimal(str(val)) if val is not None else None
    return out


def _db_bank_balances(session: Session) -> dict[str, Decimal | None]:
    return {
        row.book: row.bank_balance
        for row in session.scalars(select(ClientBookSettings)).all()
    }


def verify_rehearsal_import(
    session: Session,
    bundle_path: Path,
    *,
    expected_bhav_count: int | None = None,
) -> RehearsalVerification:
    """Compare target DB against migration bundle expectations."""
    bundle = load_migration_bundle(bundle_path)
    result = RehearsalVerification()

    for domain, model in (
        ("client_positions", ClientPosition),
        ("client_book_settings", ClientBookSettings),
        ("securities", Security),
        ("pivot_portfolio_symbols", PivotPortfolioSymbol),
        ("charts_range_rows", ChartsRangeRow),
        ("watchlist_members", WatchlistMember),
    ):
        expected = _bundle_domain_count(bundle, domain)
        actual = _db_count(session, model)
        result.checks.append(
            CheckResult(
                name=f"{domain}_count",
                ok=actual == expected,
                detail=f"expected {expected}, got {actual}",
            )
        )

    bundle_qty = _bundle_qty_sum_by_book(bundle)
    db_qty = _qty_sum_by_book(session)
    qty_ok = bundle_qty == db_qty
    result.checks.append(
        CheckResult(
            name="client_positions_qty_by_book",
            ok=qty_ok,
            detail=f"bundle={bundle_qty}, db={db_qty}",
        )
    )

    bundle_bank = _bundle_bank_balances(bundle)
    db_bank = _db_bank_balances(session)
    bank_ok = bundle_bank == db_bank
    result.checks.append(
        CheckResult(
            name="client_book_settings_balances",
            ok=bank_ok,
            detail=f"bundle={bundle_bank}, db={db_bank}",
        )
    )

    excluded = int(bundle.get("excluded_count") or len(bundle.get("excluded") or []))
    result.checks.append(
        CheckResult(
            name="bundle_excluded_documented",
            ok=True,
            detail=f"{excluded} entities excluded from bundle (value_conflict policy)",
        )
    )

    if expected_bhav_count is not None:
        actual_bhav = bhav_bar_count(session)
        result.checks.append(
            CheckResult(
                name="nse_bhav_bars_count",
                ok=actual_bhav == expected_bhav_count,
                detail=f"expected {expected_bhav_count}, got {actual_bhav}",
            )
        )

    return result
