"""Proposed migration bundle excluding unresolved conflicts."""

from __future__ import annotations

import json
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
from pms_platform.reconciliation.types import Classification, ReconReport


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def conflict_entity_keys(report: ReconReport) -> set[tuple[str, str]]:
    """Entity keys with any unresolved value conflict."""
    keys: set[tuple[str, str]] = set()
    for row in report.rows:
        if row.classification == Classification.VALUE_CONFLICT:
            keys.add((row.domain, row.key))
    return keys


def _merge_scalar(a: Any, b: Any) -> Any:
    if a == b:
        return a
    if a is None:
        return b
    if b is None:
        return a
    raise ValueError("unresolved scalar conflict")


def _merge_maps(
    samir: dict[str, dict[str, Any]],
    julesh: dict[str, dict[str, Any]],
    *,
    domain: str,
    blocked: set[tuple[str, str]],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    merged: dict[str, dict[str, Any]] = {}
    excluded: list[dict[str, str]] = []
    for key in sorted(set(samir) | set(julesh)):
        display = key
        if (domain, display) in blocked:
            excluded.append({"domain": domain, "key": display, "reason": "value_conflict"})
            continue
        s_row = samir.get(key)
        j_row = julesh.get(key)
        if s_row is None:
            merged[key] = {**j_row, "_source": "julesh"}
            continue
        if j_row is None:
            merged[key] = {**s_row, "_source": "samir"}
            continue
        fields = sorted(set(s_row) | set(j_row))
        try:
            merged[key] = {
                field: _merge_scalar(s_row.get(field), j_row.get(field)) for field in fields
            }
            merged[key]["_source"] = "both"
        except ValueError:
            excluded.append({"domain": domain, "key": display, "reason": "merge_failed"})
    return merged, excluded


def build_migration_bundle(
    report: ReconReport,
    samir: Session,
    julesh: Session,
) -> dict[str, Any]:
    """Merge Samir + Julesh snapshots; drop entities with reported value conflicts."""
    blocked = conflict_entity_keys(report)
    bundle: dict[str, Any] = {
        "policy": "Exclude entities with value_conflict in reconciliation report.",
        "domains": {},
        "excluded": [],
    }

    def load_positions(session: Session) -> dict[str, dict[str, Any]]:
        return {
            f"{pos.book}:{pos.symbol}": {
                "book": pos.book,
                "symbol": pos.symbol,
                "qty": pos.qty,
                "mcap_factor": pos.mcap_factor,
                "index_label": pos.index_label,
            }
            for pos in session.scalars(select(ClientPosition)).all()
        }

    merged, ex = _merge_maps(
        load_positions(samir),
        load_positions(julesh),
        domain="client_positions",
        blocked=blocked,
    )
    bundle["domains"]["client_positions"] = _json_safe(merged)
    bundle["excluded"].extend(ex)

    def load_book(session: Session) -> dict[str, dict[str, Any]]:
        return {
            row.book: {"bank_balance": row.bank_balance}
            for row in session.scalars(select(ClientBookSettings)).all()
        }

    merged, ex = _merge_maps(
        load_book(samir), load_book(julesh), domain="client_book_settings", blocked=blocked
    )
    bundle["domains"]["client_book_settings"] = _json_safe(merged)
    bundle["excluded"].extend(ex)

    def load_securities(session: Session) -> dict[str, dict[str, Any]]:
        fields = [
            "portfolio_name",
            "current_nse_symbol",
            "bse_code",
            "isin",
            "status",
            "sector",
            "industry",
        ]
        return {
            f"security_id={sec.security_id}": {f: getattr(sec, f) for f in fields}
            | {"security_id": sec.security_id}
            for sec in session.scalars(select(Security)).all()
        }

    merged, ex = _merge_maps(
        load_securities(samir),
        load_securities(julesh),
        domain="securities",
        blocked=blocked,
    )
    bundle["domains"]["securities"] = _json_safe(merged)
    bundle["excluded"].extend(ex)

    def load_pivot(session: Session) -> dict[str, dict[str, Any]]:
        return {
            f"symbol={row.symbol}": {
                "symbol": row.symbol,
                "sort_order": row.sort_order,
                "dummy": row.dummy,
                "portfolio_a": row.portfolio_a,
                "uptrend": row.uptrend,
            }
            for row in session.scalars(select(PivotPortfolioSymbol)).all()
        }

    merged, ex = _merge_maps(
        load_pivot(samir), load_pivot(julesh), domain="pivot_portfolio_symbols", blocked=blocked
    )
    bundle["domains"]["pivot_portfolio_symbols"] = _json_safe(merged)
    bundle["excluded"].extend(ex)

    def load_charts(session: Session) -> dict[str, dict[str, Any]]:
        fields = ["symbol", "high", "low", "close_override", "weekly_close"]
        return {
            f"row={row.excel_row}": {"excel_row": row.excel_row, **{f: getattr(row, f) for f in fields}}
            for row in session.scalars(select(ChartsRangeRow)).all()
        }

    merged, ex = _merge_maps(
        load_charts(samir), load_charts(julesh), domain="charts_range_rows", blocked=blocked
    )
    bundle["domains"]["charts_range_rows"] = _json_safe(merged)
    bundle["excluded"].extend(ex)

    def load_watchlists(session: Session) -> dict[str, dict[str, Any]]:
        names = {w.watchlist_id: w.name for w in session.scalars(select(Watchlist)).all()}
        out: dict[str, dict[str, Any]] = {}
        for member in session.scalars(select(WatchlistMember)).all():
            wl_name = names.get(member.watchlist_id, str(member.watchlist_id))
            identity = member.security_id or member.display_name or str(member.member_id)
            key = f"{wl_name}:{identity}"
            out[key] = {
                "watchlist": wl_name,
                "security_id": member.security_id,
                "display_name": member.display_name,
                "nse_symbol": member.nse_symbol,
                "bse_code": member.bse_code,
            }
        return out

    merged, ex = _merge_maps(
        load_watchlists(samir),
        load_watchlists(julesh),
        domain="watchlist_members",
        blocked=blocked,
    )
    bundle["domains"]["watchlist_members"] = _json_safe(merged)
    bundle["excluded"].extend(ex)

    bundle["excluded_count"] = len(bundle["excluded"])
    return bundle


def write_migration_bundle(
    report: ReconReport,
    samir: Session,
    julesh: Session,
    path: Path,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_migration_bundle(report, samir, julesh)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
