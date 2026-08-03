"""Apply proposed master edits: backup, write Excel, sync raw, reimport."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import openpyxl
from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.episodes.builder import build_episodes
from pms_platform.ingestion.securities import import_security_master
from pms_platform.ingestion.transactions import import_transaction_master
from pms_platform.masters.parser import ProposedEdit
from pms_platform.masters.paths import (
    MasterKind,
    default_sheet,
    final_master_dir,
    raw_sync_target,
    resolve_master_path,
)
from pms_platform.models import Security


@dataclass
class ApplyResult:
    applied: int
    backups: list[str] = field(default_factory=list)
    written_paths: list[str] = field(default_factory=list)
    synced_raw: list[str] = field(default_factory=list)
    import_notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    episode_count: int | None = None


def _backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.stem}.BACKUP_{stamp}{path.suffix}")
    shutil.copy2(path, backup)
    return backup


def _sync_to_raw(kind: MasterKind, source: Path) -> Path | None:
    target = raw_sync_target(kind)
    if target is None:
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        try:
            target.chmod(0o644)
        except OSError:
            pass
    shutil.copy2(source, target)
    try:
        target.chmod(0o444)
    except OSError:
        pass
    return target


def _parse_iso_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _resolve_portfolio_name(session: Session | None, stock: str) -> tuple[str, list[str]]:
    """Map NSE symbol / security id / portfolio name → portfolio name used in txn workbook."""
    warnings: list[str] = []
    key = stock.strip()
    if session is None:
        return key, warnings

    securities = list(session.scalars(select(Security)).all())
    by_portfolio = {s.portfolio_name.lower(): s for s in securities if s.portfolio_name}
    by_nse = {
        (s.current_nse_symbol or "").upper(): s
        for s in securities
        if s.current_nse_symbol
    }
    by_hist = {
        (s.historical_nse_symbol or "").upper(): s
        for s in securities
        if s.historical_nse_symbol
    }
    by_id = {s.security_id.upper(): s for s in securities}

    lowered = key.lower()
    upper = key.upper()
    match = (
        by_portfolio.get(lowered)
        or by_nse.get(upper)
        or by_hist.get(upper)
        or by_id.get(upper)
    )
    if match is None:
        warnings.append(
            f"No security master match for {key!r}; writing stock name as given"
        )
        return key, warnings
    return match.portfolio_name, warnings


def _find_security_row(
    worksheet: Any, match_key: str
) -> tuple[int, dict[str, int]] | None:
    """Return (row_number, header_index_map) for a matching security row."""
    rows = list(worksheet.iter_rows(values_only=True))
    if not rows:
        return None
    headers = [str(c).strip() if c is not None else "" for c in rows[0]]
    index = {h: i for i, h in enumerate(headers) if h}
    key = match_key.strip().lower()
    key_upper = match_key.strip().upper()

    def cell(row: tuple[Any, ...], name: str) -> str:
        idx = index.get(name)
        if idx is None or idx >= len(row):
            return ""
        value = row[idx]
        return str(value).strip() if value is not None else ""

    for row_number, row in enumerate(rows[1:], start=2):
        if not any(c is not None and str(c).strip() for c in row):
            continue
        candidates = [
            cell(row, "Security ID"),
            cell(row, "Portfolio Name"),
            cell(row, "Current NSE Symbol"),
            cell(row, "Historical NSE Symbol"),
            cell(row, "Canonical Company Name"),
        ]
        lowered = [c.lower() for c in candidates]
        uppered = [c.upper() for c in candidates]
        if key in lowered or key_upper in uppered:
            return row_number, index
    return None


def _append_transaction_row(
    path: Path,
    fields: dict[str, Any],
    *,
    portfolio_name: str,
) -> None:
    workbook = openpyxl.load_workbook(path)
    sheet_name = default_sheet(MasterKind.TRANSACTIONS)
    if sheet_name not in workbook.sheetnames:
        msg = f"Missing sheet {sheet_name} in {path}"
        raise ValueError(msg)
    worksheet = workbook[sheet_name]

    # Find next empty row (after last non-empty in first 8 cols)
    next_row = worksheet.max_row + 1
    for row_idx in range(worksheet.max_row, 1, -1):
        values = [worksheet.cell(row_idx, col).value for col in range(1, 9)]
        if any(v is not None and str(v).strip() for v in values):
            next_row = row_idx + 1
            break
    else:
        next_row = 2

    event_date = _parse_iso_date(fields["event_date"])
    qty = fields["quantity"]
    price = Decimal(str(fields["price"])) if fields.get("price") not in (None, "") else None
    amount = Decimal(str(fields["amount"])) if fields.get("amount") not in (None, "") else None
    if amount is None and price is not None:
        amount = Decimal(str(qty)) * price

    worksheet.cell(next_row, 1, None)  # Sr No
    worksheet.cell(next_row, 2, portfolio_name)
    worksheet.cell(next_row, 3, event_date)
    worksheet.cell(next_row, 4, fields["event_type"])
    worksheet.cell(next_row, 5, qty)
    worksheet.cell(next_row, 6, float(price) if price is not None else None)
    worksheet.cell(next_row, 7, float(amount) if amount is not None else None)
    worksheet.cell(next_row, 8, fields.get("source_note"))
    workbook.save(path)
    workbook.close()


def _update_security_row(path: Path, fields: dict[str, Any]) -> None:
    workbook = openpyxl.load_workbook(path)
    sheet_name = default_sheet(MasterKind.SECURITY)
    worksheet = workbook[sheet_name]
    found = _find_security_row(worksheet, str(fields["match_key"]))
    if found is None:
        workbook.close()
        msg = f"Security not found for match_key={fields['match_key']!r}"
        raise ValueError(msg)
    row_number, index = found

    column_map = {
        "portfolio_name": "Portfolio Name",
        "canonical_name": "Canonical Company Name",
        "current_nse_symbol": "Current NSE Symbol",
        "historical_nse_symbol": "Historical NSE Symbol",
        "bse_code": "BSE Code",
        "isin": "ISIN",
        "status": "Current Status",
        "corporate_history": "Corporate / Name History Notes",
        "sector": "Sector",
        "industry": "Industry",
        "verification_status": "Verification Status",
    }
    for field_name, header in column_map.items():
        if field_name not in fields or field_name == "match_key":
            continue
        col = index.get(header)
        if col is None:
            continue
        worksheet.cell(row_number, col + 1, fields[field_name])
    workbook.save(path)
    workbook.close()


def _append_sell_since_row(path: Path, fields: dict[str, Any]) -> None:
    workbook = openpyxl.load_workbook(path)
    sheet_name = default_sheet(MasterKind.SELL_SINCE)
    worksheet = workbook[sheet_name]
    next_row = worksheet.max_row + 1
    for row_idx in range(worksheet.max_row, 1, -1):
        values = [worksheet.cell(row_idx, col).value for col in range(1, 14)]
        if any(v is not None and str(v).strip() for v in values):
            next_row = row_idx + 1
            break
    else:
        next_row = 2

    sell_date = _parse_iso_date(fields["sell_date"])
    current_date = (
        _parse_iso_date(fields["current_date"]) if fields.get("current_date") else None
    )

    def num(key: str) -> float | None:
        value = fields.get(key)
        if value in (None, ""):
            return None
        return float(Decimal(str(value)))

    worksheet.cell(next_row, 1, fields["stock"])
    worksheet.cell(next_row, 2, sell_date)
    worksheet.cell(next_row, 3, num("sell_price"))
    worksheet.cell(next_row, 4, num("then_portfolio_value"))
    worksheet.cell(next_row, 6, current_date)
    worksheet.cell(next_row, 7, num("current_price"))
    worksheet.cell(next_row, 8, num("current_portfolio_value"))
    worksheet.cell(next_row, 13, fields.get("source_note"))
    workbook.save(path)
    workbook.close()


def apply_edits(
    session: Session,
    edits: list[ProposedEdit],
    *,
    master_dir: Path | None = None,
    reimport: bool = True,
) -> ApplyResult:
    """Backup, write Final Master Excel, sync to data/raw, reimport as needed."""
    result = ApplyResult(applied=0)
    if not edits:
        result.errors.append("No edits to apply")
        return result

    root = master_dir or final_master_dir()
    # Group by kind so we backup each file once.
    by_kind: dict[MasterKind, list[ProposedEdit]] = {}
    for edit in edits:
        by_kind.setdefault(edit.kind, []).append(edit)

    touched_reimport: set[MasterKind] = set()

    for kind, kind_edits in by_kind.items():
        path = resolve_master_path(kind, root)
        if not path.is_file():
            result.errors.append(f"Workbook missing for {kind.value}: {path}")
            continue
        try:
            backup = _backup(path)
            result.backups.append(str(backup))
        except OSError as exc:
            result.errors.append(f"Backup failed for {path}: {exc}")
            continue

        for edit in kind_edits:
            try:
                if edit.action == "append_transaction":
                    portfolio, warnings = _resolve_portfolio_name(
                        session, str(edit.fields.get("portfolio_name", ""))
                    )
                    edit.warnings.extend(warnings)
                    _append_transaction_row(path, edit.fields, portfolio_name=portfolio)
                    touched_reimport.add(MasterKind.TRANSACTIONS)
                elif edit.action == "update_security":
                    _update_security_row(path, edit.fields)
                    touched_reimport.add(MasterKind.SECURITY)
                elif edit.action == "append_sell_since":
                    _append_sell_since_row(path, edit.fields)
                else:
                    raise ValueError(f"Unknown action: {edit.action}")
                result.applied += 1
            except Exception as exc:  # noqa: BLE001
                result.errors.append(
                    f"Failed line {edit.line_number} ({edit.summary}): {exc}"
                )

        result.written_paths.append(str(path))
        synced = _sync_to_raw(kind, path)
        if synced is not None:
            result.synced_raw.append(str(synced))

    if not reimport:
        return result

    if MasterKind.SECURITY in touched_reimport:
        raw = raw_sync_target(MasterKind.SECURITY)
        if raw and raw.is_file():
            try:
                # Ensure writable for checksum read; importer only reads.
                sec = import_security_master(session, raw)
                result.import_notes.append(
                    f"security: inserted={sec.inserted} updated={sec.updated} "
                    f"skipped={sec.skipped}"
                )
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"Security reimport failed: {exc}")

    if MasterKind.TRANSACTIONS in touched_reimport:
        raw = raw_sync_target(MasterKind.TRANSACTIONS)
        if raw and raw.is_file():
            try:
                txn = import_transaction_master(session, raw)
                result.import_notes.append(
                    f"transactions: equity_inserted={txn.equity_inserted} "
                    f"equity_skipped={txn.equity_skipped} "
                    f"liquid_inserted={txn.liquid_inserted}"
                )
                episodes, decisions = build_episodes(session)
                result.episode_count = len(episodes)
                result.import_notes.append(
                    f"episodes rebuilt: episodes={len(episodes)} decisions={len(decisions)}"
                )
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"Transaction reimport failed: {exc}")

    session.flush()
    return result
