"""Compare Research workbook rows against legacy DB snapshots (read-only)."""

from __future__ import annotations

from pathlib import Path

import openpyxl
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pms_platform.ingestion.transactions import parse_transaction_workbook
from pms_platform.masters.paths import MasterKind, _TXN_CANDIDATES, resolve_master_path
from pms_platform.models.security import Security
from pms_platform.models.transaction import Transaction
from pms_platform.reconciliation.types import Classification, ReconRow


def _portfolio_dir(research_dir: Path | None) -> Path | None:
    if research_dir is None:
        return None
    nested = research_dir / "Portfolio"
    return nested if nested.is_dir() else research_dir


def _resolve_txn_path(portfolio: Path) -> Path | None:
    for name in _TXN_CANDIDATES:
        hit = portfolio / name
        if hit.is_file():
            return hit
    return None


def _security_workbook_path(portfolio: Path) -> Path | None:
    hit = portfolio / "SECURITY_MASTER_V1.xlsx"
    return hit if hit.is_file() else None


def _portfolio_names_from_security_workbook(path: Path) -> set[str]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    worksheet = workbook["Security Master"]
    names: set[str] = set()
    for row in worksheet.iter_rows(min_row=2, values_only=True):
        if len(row) < 2 or row[1] is None:
            continue
        text = str(row[1]).strip()
        if text:
            names.add(text)
    workbook.close()
    return names


def _db_portfolio_names(session: Session) -> set[str]:
    return {
        str(name).strip()
        for name in session.scalars(select(Security.portfolio_name)).all()
        if name
    }


def compare_research_masters(
    research_dir: Path | None,
    samir: Session,
    julesh: Session,
    *,
    max_name_rows: int = 200,
) -> list[ReconRow]:
    """Row/name-level Research checks vs both DB snapshots."""
    rows: list[ReconRow] = []
    portfolio = _portfolio_dir(research_dir)
    if portfolio is None:
        rows.append(
            ReconRow(
                domain="research_masters",
                key="__missing__",
                classification=Classification.IGNORED,
                notes="research_dir not provided",
            )
        )
        return rows

    sec_path = _security_workbook_path(portfolio)
    if sec_path is None:
        try:
            candidate = resolve_master_path(MasterKind.SECURITY)
            sec_path = candidate if candidate.is_file() else None
        except Exception:  # noqa: BLE001
            sec_path = None
    if sec_path is None or not sec_path.is_file():
        rows.append(
            ReconRow(
                domain="research_masters",
                key="security_master",
                classification=Classification.INVALID,
                notes="Security Master workbook not found",
            )
        )
    else:
        research_names = _portfolio_names_from_security_workbook(sec_path)
        samir_names = _db_portfolio_names(samir)
        julesh_names = _db_portfolio_names(julesh)
        union_db = samir_names | julesh_names
        only_research = sorted(research_names - union_db)
        rows.append(
            ReconRow(
                domain="research_masters",
                key="security_master:count",
                classification=Classification.IDENTICAL
                if len(research_names) == len(union_db)
                else Classification.VALUE_CONFLICT,
                samir_value=len(samir_names),
                julesh_value=len(julesh_names),
                notes=f"research_names={len(research_names)}",
            )
        )
        for name in only_research[:max_name_rows]:
            rows.append(
                ReconRow(
                    domain="research_masters",
                    key=f"portfolio_name={name}",
                    classification=Classification.ONLY_IN_RESEARCH,
                    samir_value=name,
                    notes=str(sec_path),
                )
            )
        if len(only_research) > max_name_rows:
            rows.append(
                ReconRow(
                    domain="research_masters",
                    key="__truncated_names__",
                    classification=Classification.IGNORED,
                    notes=f"listed {max_name_rows} of {len(only_research)} only-in-research names",
                )
            )

    txn_path = _resolve_txn_path(portfolio)
    if txn_path is None or not txn_path.is_file():
        rows.append(
            ReconRow(
                domain="research_masters",
                key="transactions_master",
                classification=Classification.INVALID,
                notes="Transaction master workbook not found",
            )
        )
    else:
        parsed, _skipped = parse_transaction_workbook(txn_path)
        research_txn = len(parsed)
        samir_txn = samir.scalar(select(func.count()).select_from(Transaction))
        julesh_txn = julesh.scalar(select(func.count()).select_from(Transaction))
        max_db = max(samir_txn or 0, julesh_txn or 0)
        if research_txn > max_db:
            cls = Classification.ONLY_IN_RESEARCH
        elif research_txn == samir_txn == julesh_txn:
            cls = Classification.IDENTICAL
        else:
            cls = Classification.VALUE_CONFLICT
        rows.append(
            ReconRow(
                domain="research_masters",
                key="transactions:count",
                classification=cls,
                samir_value=samir_txn,
                julesh_value=julesh_txn,
                notes=f"research_rows={research_txn}",
            )
        )
    return rows
