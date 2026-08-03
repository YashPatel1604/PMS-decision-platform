"""Rule-based prompt parser for Final Master edits (no LLM)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pms_platform.masters.paths import MasterKind
from pms_platform.models.enums import EventType

EditAction = Literal[
    "append_transaction",
    "update_security",
    "append_sell_since",
]


@dataclass
class ProposedEdit:
    action: EditAction
    kind: MasterKind
    line_number: int
    raw_line: str
    fields: dict[str, Any]
    summary: str
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParseResult:
    edits: list[ProposedEdit]
    errors: list[str]


_KV_RE = re.compile(r"(\w+)=([^\s]+)")
_DATE_RE = re.compile(
    r"(?P<y>\d{4})-(?P<m>\d{1,2})-(?P<d>\d{1,2})"
    r"|(?P<d2>\d{1,2})[/-](?P<m2>\d{1,2})[/-](?P<y2>\d{2,4})"
)

_TXN_RE = re.compile(
    r"^(?P<side>BUY|SELL|SPLIT|BONUS|RIGHTS|DEMERGER|MERGER|CONVERSION)\s+"
    r"(?P<stock>.+?)\s+"
    r"(?P<qty>-?\d+(?:\.\d+)?)\s*"
    r"(?:@\s*(?P<price>\d+(?:\.\d+)?))?\s*"
    r"(?:on\s+(?P<date>\S+))?"
    r"(?P<rest>.*)$",
    re.IGNORECASE,
)

_UPDATE_SEC_RE = re.compile(
    r"^UPDATE\s+SECURITY\s+(?P<key>\S+)(?P<rest>.*)$",
    re.IGNORECASE,
)

_SELL_SINCE_RE = re.compile(
    r"^(?:APPEND\s+)?SELL_SINCE\s+(?P<rest>.+)$",
    re.IGNORECASE,
)


def _parse_date(text: str) -> date:
    text = text.strip()
    match = _DATE_RE.fullmatch(text)
    if not match:
        msg = f"Invalid date: {text!r} (use YYYY-MM-DD)"
        raise ValueError(msg)
    if match.group("y"):
        return date(int(match.group("y")), int(match.group("m")), int(match.group("d")))
    year = int(match.group("y2"))
    if year < 100:
        year += 2000
    return date(year, int(match.group("m2")), int(match.group("d2")))


def _parse_decimal(text: str | None) -> Decimal | None:
    if text is None or text == "":
        return None
    try:
        return Decimal(str(text))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid number: {text!r}") from exc


def _kv_pairs(rest: str) -> dict[str, str]:
    return {m.group(1).lower(): m.group(2) for m in _KV_RE.finditer(rest or "")}


def _parse_txn_line(line: str, line_number: int) -> ProposedEdit:
    match = _TXN_RE.match(line.strip())
    if not match:
        msg = (
            "Expected: BUY|SELL <stock> <qty> [@price] [on YYYY-MM-DD] [note=...]"
        )
        raise ValueError(msg)

    side = match.group("side").strip().title()
    event = EventType.from_workbook(side)
    stock = match.group("stock").strip()
    qty = Decimal(match.group("qty"))
    price = _parse_decimal(match.group("price"))
    rest = match.group("rest") or ""
    kvs = _kv_pairs(rest)

    date_text = match.group("date") or kvs.get("on") or kvs.get("date")
    if not date_text:
        raise ValueError("Transaction line requires a date (on YYYY-MM-DD)")
    event_date = _parse_date(date_text)

    note = kvs.get("note") or kvs.get("notes")
    # Workbook convention: sells often store negative quantity.
    signed_qty = qty
    if event == EventType.SELL and qty > 0:
        signed_qty = -qty
    elif event == EventType.BUY and qty < 0:
        signed_qty = abs(qty)

    amount = None
    if price is not None:
        amount = (signed_qty * price).quantize(Decimal("0.01"))

    fields = {
        "portfolio_name": stock,
        "event_date": event_date.isoformat(),
        "event_type": event.value,
        "quantity": int(signed_qty) if signed_qty == signed_qty.to_integral_value() else float(signed_qty),
        "price": str(price) if price is not None else None,
        "amount": str(amount) if amount is not None else None,
        "source_note": note or f"Masters prompt {datetime.now().date().isoformat()}",
    }
    summary = (
        f"{event.value} {stock} qty={fields['quantity']}"
        + (f" @{price}" if price is not None else "")
        + f" on {event_date.isoformat()}"
    )
    return ProposedEdit(
        action="append_transaction",
        kind=MasterKind.TRANSACTIONS,
        line_number=line_number,
        raw_line=line,
        fields=fields,
        summary=summary,
    )


def _parse_update_security(line: str, line_number: int) -> ProposedEdit:
    match = _UPDATE_SEC_RE.match(line.strip())
    if not match:
        raise ValueError("Expected: UPDATE SECURITY <id|symbol|name> key=value ...")
    key = match.group("key").strip()
    kvs = _kv_pairs(match.group("rest") or "")
    if not kvs:
        raise ValueError("UPDATE SECURITY requires at least one field=value")

    allowed = {
        "portfolio_name",
        "canonical_name",
        "current_nse_symbol",
        "historical_nse_symbol",
        "bse_code",
        "isin",
        "status",
        "corporate_history",
        "sector",
        "industry",
        "verification_status",
        # short aliases
        "sector",
        "industry",
        "status",
        "isin",
        "symbol",
        "name",
    }
    alias = {
        "symbol": "current_nse_symbol",
        "nse": "current_nse_symbol",
        "name": "canonical_name",
        "portfolio": "portfolio_name",
    }
    fields: dict[str, Any] = {"match_key": key}
    for raw_k, value in kvs.items():
        field = alias.get(raw_k, raw_k)
        if field not in allowed and field != "match_key":
            # still allow known security columns
            if field not in {
                "portfolio_name",
                "canonical_name",
                "current_nse_symbol",
                "historical_nse_symbol",
                "bse_code",
                "isin",
                "status",
                "corporate_history",
                "sector",
                "industry",
                "verification_status",
            }:
                raise ValueError(f"Unknown security field: {raw_k}")
        fields[field] = value

    updates = {k: v for k, v in fields.items() if k != "match_key"}
    summary = f"UPDATE SECURITY {key}: " + ", ".join(f"{k}={v}" for k, v in updates.items())
    return ProposedEdit(
        action="update_security",
        kind=MasterKind.SECURITY,
        line_number=line_number,
        raw_line=line,
        fields=fields,
        summary=summary,
    )


def _parse_sell_since(line: str, line_number: int) -> ProposedEdit:
    match = _SELL_SINCE_RE.match(line.strip())
    if not match:
        raise ValueError(
            "Expected: SELL_SINCE stock=Name sell_date=YYYY-MM-DD sell_price=N ..."
        )
    kvs = _kv_pairs(match.group("rest") or "")
    stock = kvs.get("stock")
    if not stock:
        # Allow: SELL_SINCE Name sell_date=... sell_price=...
        rest = match.group("rest").strip()
        first = rest.split()[0] if rest else ""
        if first and "=" not in first:
            stock = first
            kvs = _kv_pairs(rest[len(first) :])
        else:
            raise ValueError("SELL_SINCE requires stock=Name")
    sell_date = kvs.get("sell_date") or kvs.get("date")
    sell_price = kvs.get("sell_price") or kvs.get("price")
    if not sell_date or not sell_price:
        raise ValueError("SELL_SINCE requires sell_date and sell_price")

    fields = {
        "stock": stock.replace("_", " "),
        "sell_date": _parse_date(sell_date).isoformat(),
        "sell_price": str(_parse_decimal(sell_price)),
        "then_portfolio_value": kvs.get("then_portfolio_value") or kvs.get("then_pv"),
        "current_date": kvs.get("current_date"),
        "current_price": kvs.get("current_price"),
        "current_portfolio_value": kvs.get("current_portfolio_value") or kvs.get("current_pv"),
        "source_note": kvs.get("note") or kvs.get("notes"),
    }
    if fields["current_date"]:
        fields["current_date"] = _parse_date(fields["current_date"]).isoformat()
    summary = (
        f"SELL_SINCE {fields['stock']} sell={fields['sell_date']} "
        f"@{fields['sell_price']}"
    )
    return ProposedEdit(
        action="append_sell_since",
        kind=MasterKind.SELL_SINCE,
        line_number=line_number,
        raw_line=line,
        fields=fields,
        summary=summary,
    )


def parse_prompt(
    prompt: str,
    *,
    kind: MasterKind | None = None,
) -> ParseResult:
    """Parse a multi-line prompt into proposed edits. Errors do not block other lines."""
    edits: list[ProposedEdit] = []
    errors: list[str] = []

    for line_number, raw in enumerate(prompt.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            upper = line.upper()
            if upper.startswith("UPDATE SECURITY"):
                edit = _parse_update_security(line, line_number)
            elif upper.startswith("SELL_SINCE") or upper.startswith("APPEND SELL_SINCE"):
                edit = _parse_sell_since(line, line_number)
            elif _TXN_RE.match(line):
                edit = _parse_txn_line(line, line_number)
            else:
                raise ValueError(
                    "Unrecognized line. Use BUY/SELL ..., UPDATE SECURITY ..., or SELL_SINCE ..."
                )
            if kind is not None and edit.kind != kind:
                raise ValueError(
                    f"Line targets {edit.kind.value} but active workbook is {kind.value}"
                )
            edits.append(edit)
        except Exception as exc:  # noqa: BLE001 - collect per-line errors
            errors.append(f"Line {line_number}: {exc}")

    return ParseResult(edits=edits, errors=errors)


def edit_to_dict(edit: ProposedEdit) -> dict[str, Any]:
    return {
        "action": edit.action,
        "kind": edit.kind.value,
        "line_number": edit.line_number,
        "raw_line": edit.raw_line,
        "fields": edit.fields,
        "summary": edit.summary,
        "warnings": edit.warnings,
    }


def edit_from_dict(payload: dict[str, Any]) -> ProposedEdit:
    return ProposedEdit(
        action=payload["action"],
        kind=MasterKind(payload["kind"]),
        line_number=int(payload.get("line_number") or 0),
        raw_line=str(payload.get("raw_line") or ""),
        fields=dict(payload.get("fields") or {}),
        summary=str(payload.get("summary") or ""),
        warnings=list(payload.get("warnings") or []),
    )
