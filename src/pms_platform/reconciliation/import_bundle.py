"""Apply migration_bundle.json to a target database (Phase 8 rehearsal / cutover)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.models.charts_range import ChartsRangeRow
from pms_platform.models.client_book_settings import ClientBookSettings
from pms_platform.models.client_position import ClientPosition
from pms_platform.models.nse_bhav import PivotPortfolioSymbol
from pms_platform.models.security import Security
from pms_platform.models.watchlist import Watchlist, WatchlistMember


@dataclass
class DomainImportStats:
    domain: str
    inserted: int = 0
    updated: int = 0
    skipped: int = 0


@dataclass
class BundleImportResult:
    bundle_path: str
    dry_run: bool
    domains: list[DomainImportStats] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "bundle_path": self.bundle_path,
            "dry_run": self.dry_run,
            "domains": [
                {
                    "domain": d.domain,
                    "inserted": d.inserted,
                    "updated": d.updated,
                    "skipped": d.skipped,
                }
                for d in self.domains
            ],
        }


def _dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _row_without_meta(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if not k.startswith("_")}


def _import_client_positions(session: Session, rows: dict[str, Any], *, dry_run: bool) -> DomainImportStats:
    stats = DomainImportStats(domain="client_positions")
    for row in rows.values():
        data = _row_without_meta(row)
        book = data["book"]
        symbol = data["symbol"]
        existing = session.scalar(
            select(ClientPosition).where(
                ClientPosition.book == book,
                ClientPosition.symbol == symbol,
            )
        )
        if existing is None:
            stats.inserted += 1
            if not dry_run:
                session.add(
                    ClientPosition(
                        book=book,
                        symbol=symbol,
                        qty=_dec(data["qty"]) or Decimal("0"),
                        mcap_factor=_dec(data.get("mcap_factor")),
                        index_label=data.get("index_label"),
                        row_version=1,
                    )
                )
        else:
            stats.updated += 1
            if not dry_run:
                existing.qty = _dec(data["qty"]) or Decimal("0")
                existing.mcap_factor = _dec(data.get("mcap_factor"))
                existing.index_label = data.get("index_label")
    return stats


def _import_client_book_settings(
    session: Session, rows: dict[str, Any], *, dry_run: bool
) -> DomainImportStats:
    stats = DomainImportStats(domain="client_book_settings")
    for book, row in rows.items():
        data = _row_without_meta(row)
        book_key = data.get("book", book.split(":")[-1] if ":" in book else book)
        existing = session.get(ClientBookSettings, book_key)
        balance = _dec(data.get("bank_balance"))
        if existing is None:
            stats.inserted += 1
            if not dry_run:
                session.add(
                    ClientBookSettings(book=book_key, bank_balance=balance, row_version=1)
                )
        else:
            stats.updated += 1
            if not dry_run:
                existing.bank_balance = balance
    return stats


def _import_securities(session: Session, rows: dict[str, Any], *, dry_run: bool) -> DomainImportStats:
    stats = DomainImportStats(domain="securities")
    fields = [
        "portfolio_name",
        "current_nse_symbol",
        "bse_code",
        "isin",
        "status",
        "sector",
        "industry",
    ]
    for row in rows.values():
        data = _row_without_meta(row)
        sec_id = data["security_id"]
        existing = session.get(Security, sec_id)
        if existing is None:
            stats.inserted += 1
            if not dry_run:
                session.add(
                    Security(
                        security_id=sec_id,
                        portfolio_name=data.get("portfolio_name") or sec_id,
                        current_nse_symbol=data.get("current_nse_symbol"),
                        bse_code=data.get("bse_code"),
                        isin=data.get("isin"),
                        status=data.get("status"),
                        sector=data.get("sector"),
                        industry=data.get("industry"),
                    )
                )
        else:
            stats.updated += 1
            if not dry_run:
                for field in fields:
                    if field in data and data[field] is not None:
                        setattr(existing, field, data[field])
    return stats


def _import_pivot(session: Session, rows: dict[str, Any], *, dry_run: bool) -> DomainImportStats:
    stats = DomainImportStats(domain="pivot_portfolio_symbols")
    for row in rows.values():
        data = _row_without_meta(row)
        symbol = data["symbol"]
        existing = session.get(PivotPortfolioSymbol, symbol)
        if existing is None:
            stats.inserted += 1
            if not dry_run:
                session.add(
                    PivotPortfolioSymbol(
                        symbol=symbol,
                        sort_order=int(data.get("sort_order") or 0),
                        dummy=bool(data.get("dummy")),
                        portfolio_a=bool(data.get("portfolio_a")),
                        uptrend=bool(data.get("uptrend")),
                    )
                )
        else:
            stats.updated += 1
            if not dry_run:
                existing.sort_order = int(data.get("sort_order") or 0)
                existing.dummy = bool(data.get("dummy"))
                existing.portfolio_a = bool(data.get("portfolio_a"))
                existing.uptrend = bool(data.get("uptrend"))
    return stats


def _import_charts(session: Session, rows: dict[str, Any], *, dry_run: bool) -> DomainImportStats:
    stats = DomainImportStats(domain="charts_range_rows")
    for row in rows.values():
        data = _row_without_meta(row)
        excel_row = int(data["excel_row"])
        symbol = data["symbol"]
        existing = session.get(ChartsRangeRow, excel_row)
        if existing is None:
            stats.inserted += 1
            if not dry_run:
                session.add(
                    ChartsRangeRow(
                        excel_row=excel_row,
                        symbol=symbol,
                        name=data.get("name") or symbol,
                        section=data.get("section") or "holdings",
                        high=_dec(data.get("high")),
                        low=_dec(data.get("low")),
                        close_override=_dec(data.get("close_override")),
                        weekly_close=_dec(data.get("weekly_close")),
                        row_version=1,
                    )
                )
        else:
            stats.updated += 1
            if not dry_run:
                existing.symbol = symbol
                existing.high = _dec(data.get("high"))
                existing.low = _dec(data.get("low"))
                existing.close_override = _dec(data.get("close_override"))
                existing.weekly_close = _dec(data.get("weekly_close"))
    return stats


def _import_watchlist_members(
    session: Session, rows: dict[str, Any], *, dry_run: bool
) -> DomainImportStats:
    stats = DomainImportStats(domain="watchlist_members")
    watchlists: dict[str, Watchlist] = {}
    for row in rows.values():
        data = _row_without_meta(row)
        wl_name = data["watchlist"]
        if wl_name not in watchlists:
            wl = session.scalar(select(Watchlist).where(Watchlist.name == wl_name))
            if wl is None:
                stats.inserted += 1
                if not dry_run:
                    wl = Watchlist(name=wl_name)
                    session.add(wl)
                    session.flush()
                else:
                    wl = Watchlist(name=wl_name)
            watchlists[wl_name] = wl
        wl = watchlists[wl_name]
        if dry_run and wl.watchlist_id is None:
            stats.inserted += 1
            continue

        security_id = data.get("security_id")
        display_name = data.get("display_name") or security_id or "unknown"
        existing = None
        if not dry_run and wl.watchlist_id is not None:
            if security_id:
                existing = session.scalar(
                    select(WatchlistMember).where(
                        WatchlistMember.watchlist_id == wl.watchlist_id,
                        WatchlistMember.security_id == security_id,
                    )
                )
            if existing is None:
                existing = session.scalar(
                    select(WatchlistMember).where(
                        WatchlistMember.watchlist_id == wl.watchlist_id,
                        WatchlistMember.display_name == display_name,
                    )
                )
        if existing is None:
            stats.inserted += 1
            if not dry_run:
                session.add(
                    WatchlistMember(
                        watchlist_id=wl.watchlist_id,
                        security_id=security_id,
                        display_name=display_name,
                        nse_symbol=data.get("nse_symbol"),
                        bse_code=data.get("bse_code"),
                    )
                )
        else:
            stats.updated += 1
            if not dry_run:
                existing.nse_symbol = data.get("nse_symbol")
                existing.bse_code = data.get("bse_code")
                existing.display_name = display_name
    return stats


_IMPORTERS = {
    "client_positions": _import_client_positions,
    "client_book_settings": _import_client_book_settings,
    "securities": _import_securities,
    "pivot_portfolio_symbols": _import_pivot,
    "charts_range_rows": _import_charts,
    "watchlist_members": _import_watchlist_members,
}


def load_migration_bundle(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def import_migration_bundle(
    session: Session,
    bundle_path: Path,
    *,
    dry_run: bool = False,
) -> BundleImportResult:
    """Upsert bundle domains into target session. Caller commits."""
    payload = load_migration_bundle(bundle_path)
    domains = payload.get("domains") or {}
    result = BundleImportResult(bundle_path=str(bundle_path), dry_run=dry_run)
    for domain, importer in _IMPORTERS.items():
        rows = domains.get(domain) or {}
        if not rows:
            result.domains.append(DomainImportStats(domain=domain, skipped=0))
            continue
        stats = importer(session, rows, dry_run=dry_run)
        result.domains.append(stats)
    return result
