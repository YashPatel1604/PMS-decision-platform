"""Domain comparators for two legacy database snapshots."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.models.charts_range import ChartsRangeRow
from pms_platform.models.client_book_settings import ClientBookSettings
from pms_platform.models.client_position import ClientPosition
from pms_platform.models.nse_bhav import NseBhavBar
from pms_platform.models.security import Security
from pms_platform.models.watchlist import Watchlist, WatchlistMember
from pms_platform.reconciliation.types import Classification, ReconRow


def _norm_decimal(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    return str(value)


def _compare_field(
    *,
    domain: str,
    key: str,
    field: str,
    samir_val: Any,
    julesh_val: Any,
) -> ReconRow | None:
    a = _norm_decimal(samir_val)
    b = _norm_decimal(julesh_val)
    if a == b:
        return ReconRow(
            domain=domain,
            key=key,
            field=field,
            classification=Classification.IDENTICAL,
            samir_value=a,
            julesh_value=b,
        )
    if a is not None and b is not None:
        return ReconRow(
            domain=domain,
            key=key,
            field=field,
            classification=Classification.VALUE_CONFLICT,
            samir_value=a,
            julesh_value=b,
        )
    return ReconRow(
        domain=domain,
        key=key,
        field=field,
        classification=Classification.COMPATIBLE_MERGE,
        samir_value=a,
        julesh_value=b,
        notes="one side null — merge may copy non-null value",
    )


def compare_keyed_records(
    *,
    domain: str,
    samir: dict[str, dict[str, Any]],
    julesh: dict[str, dict[str, Any]],
    fields: list[str],
    key_label: Callable[[str], str] | None = None,
) -> list[ReconRow]:
    """Compare records keyed by a stable string id."""
    rows: list[ReconRow] = []
    all_keys = sorted(set(samir) | set(julesh))
    label = key_label or (lambda k: k)
    for key in all_keys:
        display = label(key)
        s_row = samir.get(key)
        j_row = julesh.get(key)
        if s_row is None:
            rows.append(
                ReconRow(
                    domain=domain,
                    key=display,
                    classification=Classification.ONLY_IN_JULESH,
                    julesh_value={f: j_row.get(f) for f in fields},
                )
            )
            continue
        if j_row is None:
            rows.append(
                ReconRow(
                    domain=domain,
                    key=display,
                    classification=Classification.ONLY_IN_SAMIR,
                    samir_value={f: s_row.get(f) for f in fields},
                )
            )
            continue
        for field in fields:
            row = _compare_field(
                domain=domain,
                key=display,
                field=field,
                samir_val=s_row.get(field),
                julesh_val=j_row.get(field),
            )
            if row is not None:
                rows.append(row)
    return rows


def compare_client_positions(samir: Session, julesh: Session) -> list[ReconRow]:
    domain = "client_positions"
    fields = ["qty", "mcap_factor", "index_label"]

    def load(session: Session) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for pos in session.scalars(select(ClientPosition)).all():
            key = f"{pos.book}:{pos.symbol}"
            out[key] = {
                "qty": pos.qty,
                "mcap_factor": pos.mcap_factor,
                "index_label": pos.index_label,
            }
        return out

    return compare_keyed_records(
        domain=domain,
        samir=load(samir),
        julesh=load(julesh),
        fields=fields,
    )


def compare_client_book_settings(samir: Session, julesh: Session) -> list[ReconRow]:
    domain = "client_book_settings"

    def load(session: Session) -> dict[str, dict[str, Any]]:
        return {
            row.book: {"bank_balance": row.bank_balance}
            for row in session.scalars(select(ClientBookSettings)).all()
        }

    return compare_keyed_records(
        domain=domain,
        samir=load(samir),
        julesh=load(julesh),
        fields=["bank_balance"],
    )


def compare_securities(samir: Session, julesh: Session) -> list[ReconRow]:
    domain = "securities"
    fields = [
        "portfolio_name",
        "current_nse_symbol",
        "bse_code",
        "isin",
        "status",
    ]

    def load(session: Session) -> dict[str, dict[str, Any]]:
        return {
            sec.security_id: {f: getattr(sec, f) for f in fields}
            for sec in session.scalars(select(Security)).all()
        }

    return compare_keyed_records(
        domain=domain,
        samir=load(samir),
        julesh=load(julesh),
        fields=fields,
        key_label=lambda k: f"security_id={k}",
    )


def compare_watchlist_members(samir: Session, julesh: Session) -> list[ReconRow]:
    domain = "watchlist_members"
    fields = ["display_name", "nse_symbol", "bse_code", "security_id"]

    def load(session: Session) -> dict[str, dict[str, Any]]:
        names = {w.watchlist_id: w.name for w in session.scalars(select(Watchlist)).all()}
        out: dict[str, dict[str, Any]] = {}
        for member in session.scalars(select(WatchlistMember)).all():
            wl_name = names.get(member.watchlist_id, str(member.watchlist_id))
            identity = member.security_id or member.display_name or str(member.member_id)
            key = f"{wl_name}:{identity}"
            out[key] = {f: getattr(member, f) for f in fields}
        return out

    return compare_keyed_records(domain=domain, samir=load(samir), julesh=load(julesh), fields=fields)


def compare_charts_range_rows(samir: Session, julesh: Session) -> list[ReconRow]:
    domain = "charts_range_rows"
    fields = ["symbol", "high", "low", "close_override", "weekly_close"]

    def load(session: Session) -> dict[str, dict[str, Any]]:
        return {
            str(row.excel_row): {f: getattr(row, f) for f in fields}
            for row in session.scalars(select(ChartsRangeRow)).all()
        }

    return compare_keyed_records(
        domain=domain,
        samir=load(samir),
        julesh=load(julesh),
        fields=fields,
        key_label=lambda k: f"row={k}",
    )


def compare_bhav_bars(samir: Session, julesh: Session, *, max_conflicts: int = 500) -> list[ReconRow]:
    """Compare bhav bars by (date, symbol, series); cap reported conflicts."""
    domain = "nse_bhav_bars"
    fields = ["open", "high", "low", "close"]
    rows: list[ReconRow] = []

    def load(session: Session) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for bar in session.scalars(select(NseBhavBar)).all():
            key = f"{bar.trade_date}:{bar.symbol}:{bar.series}"
            out[key] = {f: getattr(bar, f) for f in fields}
        return out

    s_map = load(samir)
    j_map = load(julesh)
    rows.append(
        ReconRow(
            domain=domain,
            key="__count__",
            classification=Classification.IDENTICAL
            if len(s_map) == len(j_map)
            else Classification.VALUE_CONFLICT,
            samir_value=len(s_map),
            julesh_value=len(j_map),
            notes="row count",
        )
    )

    conflicts = 0
    for key in sorted(set(s_map) & set(j_map)):
        if conflicts >= max_conflicts:
            rows.append(
                ReconRow(
                    domain=domain,
                    key="__truncated__",
                    classification=Classification.IGNORED,
                    notes=f"conflict listing capped at {max_conflicts}",
                )
            )
            break
        for field in fields:
            cmp_row = _compare_field(
                domain=domain,
                key=key,
                field=field,
                samir_val=s_map[key].get(field),
                julesh_val=j_map[key].get(field),
            )
            if cmp_row and cmp_row.classification == Classification.VALUE_CONFLICT:
                rows.append(cmp_row)
                conflicts += 1
    only_s = set(s_map) - set(j_map)
    only_j = set(j_map) - set(s_map)
    if only_s:
        rows.append(
            ReconRow(
                domain=domain,
                key="__only_samir__",
                classification=Classification.ONLY_IN_SAMIR,
                samir_value=len(only_s),
            )
        )
    if only_j:
        rows.append(
            ReconRow(
                domain=domain,
                key="__only_julesh__",
                classification=Classification.ONLY_IN_JULESH,
                julesh_value=len(only_j),
            )
        )
    return rows
