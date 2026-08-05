"""Corporate-action calendar for split/bonus price-unit adjustment.

Quantity truth remains the transaction ledger (Split/Bonus rows).
This calendar documents Yahoo (and ledger) split/bonus events so transaction
prices can be converted into back-adjusted daily-price series units on any
machine — including Dad's Docker host after ``git pull`` + Refresh.
"""

from __future__ import annotations

import csv
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from pathlib import Path

from pms_platform.config import settings
from pms_platform.market_data.contracts import CORPORATE_ACTIONS_COLUMNS, CanonicalPaths
from pms_platform.market_data.yahoo_finance import YahooFinanceClient

_ONE = Decimal("1")


@dataclass(frozen=True)
class CorporateAction:
    """One split/bonus (or Yahoo-encoded bonus) event."""

    security_id: str
    portfolio_name: str
    action_date: date
    action_type: str
    split_ratio: str
    numerator: Decimal
    denominator: Decimal
    share_multiplier: Decimal
    yahoo_ticker: str
    source: str
    in_transaction_ledger: bool
    held_through: bool
    pre_qty: int
    quantity_delta: int
    notes: str


def resolve_corporate_actions_path(external_dir: Path | None = None) -> Path | None:
    """Prefer external_dir, then settings.external_data_dir, then Docker seed."""
    rel = CanonicalPaths().corporate_actions
    candidates: list[Path] = []
    if external_dir is not None:
        candidates.append(Path(external_dir) / rel)
    candidates.append(Path(settings.external_data_dir) / rel)
    candidates.append(Path("/data/external") / rel)
    candidates.append(Path("/data/external_seed") / rel)
    candidates.append(Path("docker/market_data_seed") / rel)
    for path in candidates:
        if path.is_file():
            return path.resolve()
    return None


def load_corporate_actions(path: Path | None = None) -> list[CorporateAction]:
    """Load the canonical corporate-actions CSV."""
    resolved = path or resolve_corporate_actions_path()
    if resolved is None:
        return []
    rows: list[CorporateAction] = []
    with resolved.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            if not raw.get("security_id") or not raw.get("action_date"):
                continue
            rows.append(
                CorporateAction(
                    security_id=str(raw["security_id"]).strip(),
                    portfolio_name=str(raw.get("portfolio_name") or "").strip(),
                    action_date=date.fromisoformat(str(raw["action_date"])[:10]),
                    action_type=str(raw.get("action_type") or "Split").strip(),
                    split_ratio=str(raw.get("split_ratio") or "").strip(),
                    numerator=Decimal(str(raw.get("numerator") or "1")),
                    denominator=Decimal(str(raw.get("denominator") or "1")),
                    share_multiplier=Decimal(str(raw.get("share_multiplier") or "1")),
                    yahoo_ticker=str(raw.get("yahoo_ticker") or "").strip(),
                    source=str(raw.get("source") or "").strip(),
                    in_transaction_ledger=str(raw.get("in_transaction_ledger") or "").lower()
                    in {"1", "true", "yes", "y"},
                    held_through=str(raw.get("held_through") or "").lower()
                    in {"1", "true", "yes", "y"},
                    pre_qty=int(float(raw.get("pre_qty") or 0)),
                    quantity_delta=int(float(raw.get("quantity_delta") or 0)),
                    notes=str(raw.get("notes") or "").strip(),
                )
            )
    return rows


@lru_cache(maxsize=1)
def _cached_actions() -> tuple[CorporateAction, ...]:
    return tuple(load_corporate_actions())


def clear_corporate_actions_cache() -> None:
    """Drop cached calendar (call after rebuilding the CSV)."""
    _cached_actions.cache_clear()


def series_unit_factor_after(
    security_id: str,
    as_of: date,
    *,
    actions: list[CorporateAction] | None = None,
) -> Decimal:
    """Factor to convert a raw trade price on ``as_of`` into adjusted series units.

    Vendor adjusted closes back-adjust for subsequent splits/bonuses, so:

        series_price ≈ raw_trade_price / Π(share_multiplier for actions after as_of)
                     = raw_trade_price * Π(1/share_multiplier)
    """
    calendar = actions if actions is not None else list(_cached_actions())
    factor = _ONE
    for action in calendar:
        if action.security_id != security_id:
            continue
        if action.action_date <= as_of:
            continue
        if action.share_multiplier <= 0:
            continue
        factor *= _ONE / action.share_multiplier
    return factor


def write_corporate_actions_csv(path: Path, rows: list[CorporateAction]) -> None:
    """Write canonical corporate-actions CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CORPORATE_ACTIONS_COLUMNS))
        writer.writeheader()
        for row in sorted(rows, key=lambda item: (item.action_date, item.portfolio_name)):
            writer.writerow(
                {
                    "security_id": row.security_id,
                    "portfolio_name": row.portfolio_name,
                    "action_date": row.action_date.isoformat(),
                    "action_type": row.action_type,
                    "split_ratio": row.split_ratio,
                    "numerator": f"{row.numerator:f}",
                    "denominator": f"{row.denominator:f}",
                    "share_multiplier": f"{row.share_multiplier:f}",
                    "yahoo_ticker": row.yahoo_ticker,
                    "source": row.source,
                    "in_transaction_ledger": "true" if row.in_transaction_ledger else "false",
                    "held_through": "true" if row.held_through else "false",
                    "pre_qty": row.pre_qty,
                    "quantity_delta": row.quantity_delta,
                    "notes": row.notes,
                }
            )


def _qty_before(
    events_by_name: dict[str, list],
    name: str,
    as_of: date,
) -> int:
    from pms_platform.models.enums import EventType

    quantity = 0
    for row in sorted(events_by_name.get(name, []), key=lambda item: (item.event_date, item.source_row)):
        if row.event_date > as_of:
            break
        if row.event_date == as_of and row.event_type in EventType.corporate_actions():
            continue
        if row.event_type == EventType.SELL:
            quantity -= abs(row.quantity)
        else:
            quantity += row.quantity
    return quantity


def build_corporate_actions_from_yahoo(
    *,
    security_master_path: Path,
    transactions_path: Path,
    client: YahooFinanceClient | None = None,
    sleep_seconds: float = 0.12,
) -> list[CorporateAction]:
    """Fetch Yahoo splits for every security that appears in the transaction master."""
    import openpyxl

    from pms_platform.ingestion.transactions import parse_transaction_workbook
    from pms_platform.models.enums import EventType

    workbook = openpyxl.load_workbook(security_master_path, read_only=True, data_only=True)
    sec_rows = list(workbook.active.iter_rows(values_only=True))
    workbook.close()

    securities: list[dict[str, str]] = []
    for row in sec_rows[1:]:
        if not row or not row[0] or not row[1]:
            continue
        securities.append(
            {
                "security_id": str(row[0]).strip(),
                "portfolio_name": str(row[1]).strip(),
                "nse": str(row[3]).strip() if row[3] else "",
                "hist_nse": str(row[4]).strip() if row[4] else "",
                "bse": str(row[5]).strip() if row[5] else "",
            }
        )

    parsed, _ = parse_transaction_workbook(transactions_path)
    events_by_name: dict[str, list] = defaultdict(list)
    for row in parsed:
        if "liquid" in row.portfolio_name.lower():
            continue
        events_by_name[row.portfolio_name].append(row)

    existing_cas = [
        row
        for row in parsed
        if row.event_type in (EventType.SPLIT, EventType.BONUS, EventType.RIGHTS)
    ]
    existing_keys = {(row.portfolio_name.lower(), row.event_date) for row in existing_cas}

    yahoo = client or YahooFinanceClient()
    results: list[CorporateAction] = []

    for sec in securities:
        name = sec["portfolio_name"]
        if name not in events_by_name:
            continue
        tickers: list[str] = []
        for symbol in (sec["nse"], sec["hist_nse"]):
            if symbol and symbol != "None":
                tickers.append(f"{symbol}.NS")
                if "&" in symbol:
                    tickers.append(f"{symbol.replace('&', '-')}.NS")
        if sec["bse"] and sec["bse"] != "None":
            tickers.append(f"{sec['bse']}.BO")

        splits = []
        used = ""
        for ticker in tickers:
            try:
                splits = yahoo.fetch_splits(ticker)
            except Exception:  # noqa: BLE001 — keep building calendar
                splits = []
            time.sleep(sleep_seconds)
            if splits:
                used = ticker
                break
        if not splits:
            continue

        for split in splits:
            pre = _qty_before(events_by_name, name, split.action_date)
            if pre <= 0:
                pre = _qty_before(events_by_name, name, split.action_date - timedelta(days=1))
            mult = split.share_multiplier
            delta = 0
            if pre > 0 and mult != _ONE:
                delta = int(
                    (Decimal(pre) * (mult - _ONE)).to_integral_value(rounding=ROUND_HALF_UP)
                )
            in_ledger = any(
                key_name == name.lower() and abs((key_date - split.action_date).days) <= 7
                for key_name, key_date in existing_keys
            )
            held = pre > 0
            action_type = "Split"
            ledger_delta = None
            if in_ledger:
                for row in existing_cas:
                    if (
                        row.portfolio_name.lower() == name.lower()
                        and abs((row.event_date - split.action_date).days) <= 7
                    ):
                        action_type = row.event_type.value
                        ledger_delta = row.quantity
                        break
            # Prefer ledger-implied share multiplier when we held through
            # (Yahoo sometimes reports only part of a split+bonus chain).
            if held and ledger_delta is not None and pre > 0:
                implied = (Decimal(pre + ledger_delta) / Decimal(pre)).normalize()
                if implied > 0:
                    mult = implied
                    delta = ledger_delta
            note_parts = [
                f"Yahoo {used} {split.split_ratio}",
                "held through" if held else "not held on action date",
                "ledger has matching Split/Bonus" if in_ledger else "no matching ledger qty event",
            ]
            if held and ledger_delta is not None:
                note_parts.append(f"ledger-implied multiplier={mult}")
            if held and not in_ledger:
                note_parts.append("QUANTITY GAP — add Split/Bonus row to transactions master")
            results.append(
                CorporateAction(
                    security_id=sec["security_id"],
                    portfolio_name=name,
                    action_date=split.action_date,
                    action_type=action_type,
                    split_ratio=split.split_ratio,
                    numerator=split.numerator,
                    denominator=split.denominator,
                    share_multiplier=mult,
                    yahoo_ticker=used,
                    source="YAHOO_FINANCE",
                    in_transaction_ledger=in_ledger,
                    held_through=held,
                    pre_qty=pre,
                    quantity_delta=delta,
                    notes="; ".join(note_parts),
                )
            )

    # Append ledger Rights/Demerger not represented as Yahoo splits
    from pms_platform.models.enums import EventType as ET

    yahoo_keys = {(row.portfolio_name.lower(), row.action_date) for row in results}
    name_to_sec = {sec["portfolio_name"]: sec for sec in securities}
    for row in parsed:
        if row.event_type not in (ET.RIGHTS, ET.DEMERGER, ET.SPLIT, ET.BONUS):
            continue
        if any(
            key_name == row.portfolio_name.lower() and abs((key_date - row.event_date).days) <= 7
            for key_name, key_date in yahoo_keys
        ):
            continue
        sec = name_to_sec.get(row.portfolio_name)
        if sec is None:
            continue
        pre = _qty_before(events_by_name, row.portfolio_name, row.event_date)
        results.append(
            CorporateAction(
                security_id=sec["security_id"],
                portfolio_name=row.portfolio_name,
                action_date=row.event_date,
                action_type=row.event_type.value,
                split_ratio="",
                numerator=_ONE,
                denominator=_ONE,
                share_multiplier=_ONE,
                yahoo_ticker="",
                source="TRANSACTION_LEDGER",
                in_transaction_ledger=True,
                held_through=pre > 0,
                pre_qty=pre,
                quantity_delta=row.quantity,
                notes=(row.source_note or "Ledger-only corporate action"),
            )
        )

    clear_corporate_actions_cache()
    return results
