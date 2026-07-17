"""Identifier resolution for market-data imports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.market_data.contracts import UNCONFIRMED_SUCCESSOR_PORTFOLIO_NAMES
from pms_platform.models import Security, SecuritySuccessor, SecuritySymbolHistory


@dataclass(frozen=True)
class IdentifierResolution:
    """Outcome of resolving a market-data identifier to a security."""

    security_id: str | None
    status: str
    message: str | None = None


def _symbol_active(
    effective_from: date,
    effective_to: date | None,
    as_of_date: date,
) -> bool:
    if as_of_date < effective_from:
        return False
    return effective_to is None or as_of_date <= effective_to


class IdentifierResolver:
    """Resolve canonical identifiers to securities using dated symbol history."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._securities = list(session.scalars(select(Security)).all())
        self._symbol_history = list(session.scalars(select(SecuritySymbolHistory)).all())
        self._successors = list(session.scalars(select(SecuritySuccessor)).all())
        self._security_by_id = {security.security_id: security for security in self._securities}

    def resolve(
        self,
        identifier_type: str,
        identifier: str,
        as_of_date: date,
    ) -> IdentifierResolution:
        """Resolve an identifier as of a trade or event date."""
        normalized_type = identifier_type.strip().upper()
        normalized_identifier = identifier.strip()

        if normalized_type == "SECURITY_ID":
            return self._resolve_security_id(normalized_identifier, as_of_date)

        security_ids = self._lookup_symbol_history(
            normalized_type, normalized_identifier, as_of_date
        )
        if len(security_ids) == 1:
            return self._finalize_resolution(next(iter(security_ids)), as_of_date)

        if len(security_ids) > 1:
            return IdentifierResolution(
                security_id=None,
                status="AMBIGUOUS",
                message=f"Ambiguous {normalized_type}={normalized_identifier} on {as_of_date}",
            )

        fallback_ids = self._lookup_security_master(normalized_type, normalized_identifier)
        if len(fallback_ids) == 1:
            return self._finalize_resolution(next(iter(fallback_ids)), as_of_date)
        if len(fallback_ids) > 1:
            return IdentifierResolution(
                security_id=None,
                status="AMBIGUOUS",
                message=f"Ambiguous {normalized_type}={normalized_identifier}",
            )

        return IdentifierResolution(
            security_id=None,
            status="UNKNOWN",
            message=f"Unknown {normalized_type}={normalized_identifier}",
        )

    def _resolve_security_id(self, security_id: str, as_of_date: date) -> IdentifierResolution:
        if security_id not in self._security_by_id:
            return IdentifierResolution(
                security_id=None,
                status="UNKNOWN",
                message=f"Unknown SECURITY_ID={security_id}",
            )
        return self._finalize_resolution(security_id, as_of_date)

    def _lookup_symbol_history(
        self,
        identifier_type: str,
        identifier: str,
        as_of_date: date,
    ) -> set[str]:
        symbol_type = _to_symbol_type(identifier_type)
        if symbol_type is None:
            return set()

        matches: set[str] = set()
        for row in self._symbol_history:
            if row.symbol_type != symbol_type:
                continue
            if row.symbol.strip().upper() != identifier.upper():
                continue
            if _symbol_active(row.effective_from, row.effective_to, as_of_date):
                matches.add(row.security_id)
        return matches

    def _lookup_security_master(self, identifier_type: str, identifier: str) -> set[str]:
        matches: set[str] = set()
        for security in self._securities:
            if identifier_type == "NSE_SYMBOL":
                symbols = {
                    value.strip().upper()
                    for value in (
                        security.current_nse_symbol,
                        security.historical_nse_symbol,
                    )
                    if value
                }
                if identifier.upper() in symbols:
                    matches.add(security.security_id)
            elif identifier_type == "BSE_CODE" and security.bse_code:
                if security.bse_code.strip() == identifier.strip():
                    matches.add(security.security_id)
            elif identifier_type == "ISIN" and security.isin:
                if security.isin.strip().upper() == identifier.upper():
                    matches.add(security.security_id)
            elif identifier_type == "PORTFOLIO_NAME":
                if security.portfolio_name.strip().upper() == identifier.upper():
                    matches.add(security.security_id)
        return matches

    def _finalize_resolution(self, security_id: str, as_of_date: date) -> IdentifierResolution:
        security = self._security_by_id[security_id]
        if security.portfolio_name in UNCONFIRMED_SUCCESSOR_PORTFOLIO_NAMES:
            return IdentifierResolution(
                security_id=security_id,
                status="INSUFFICIENT",
                message=(
                    f"Security {security.portfolio_name} requires confirmed successor mapping"
                ),
            )

        predecessor = self._find_predecessor(security_id, as_of_date)
        if predecessor is not None:
            predecessor_security = self._security_by_id[predecessor.predecessor_security_id]
            if not predecessor.confirmed:
                return IdentifierResolution(
                    security_id=security_id,
                    status="INSUFFICIENT",
                    message=(
                        "Unconfirmed successor chain for "
                        f"{predecessor_security.portfolio_name} -> {security.portfolio_name}"
                    ),
                )
        return IdentifierResolution(security_id=security_id, status="RESOLVED")

    def _find_predecessor(self, security_id: str, as_of_date: date) -> SecuritySuccessor | None:
        candidates = [
            row
            for row in self._successors
            if row.successor_security_id == security_id and row.effective_date <= as_of_date
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda row: row.effective_date)


def _to_symbol_type(identifier_type: str) -> str | None:
    mapping = {
        "NSE_SYMBOL": "NSE",
        "BSE_CODE": "BSE",
        "ISIN": "ISIN",
        "PORTFOLIO_NAME": "PORTFOLIO_NAME",
    }
    return mapping.get(identifier_type)


def bootstrap_symbol_history_from_securities(
    session: Session,
    *,
    source_file: str,
    import_batch_id: int,
    effective_from: date = date(2012, 1, 1),
) -> int:
    """Seed dated symbol history rows from the Security Master."""
    from pms_platform.market_data.common import make_csv_source_key

    inserted = 0
    securities = session.scalars(select(Security)).all()
    for index, security in enumerate(securities, start=1):
        symbol_rows: list[tuple[str, str]] = []
        if security.current_nse_symbol:
            symbol_rows.append(("NSE", security.current_nse_symbol.strip()))
        if security.historical_nse_symbol:
            historical = security.historical_nse_symbol.strip()
            if historical not in {symbol for _, symbol in symbol_rows}:
                symbol_rows.append(("NSE", historical))
        if security.bse_code:
            symbol_rows.append(("BSE", security.bse_code.strip()))
        if security.isin:
            symbol_rows.append(("ISIN", security.isin.strip()))
        symbol_rows.append(("PORTFOLIO_NAME", security.portfolio_name.strip()))

        for symbol_type, symbol in symbol_rows:
            source_key = make_csv_source_key(
                f"{source_file}|bootstrap|{security.security_id}|{symbol_type}|{symbol}",
                index,
            )
            existing = session.scalar(
                select(SecuritySymbolHistory).where(SecuritySymbolHistory.source_key == source_key)
            )
            if existing is not None:
                continue
            session.add(
                SecuritySymbolHistory(
                    security_id=security.security_id,
                    symbol_type=symbol_type,
                    symbol=symbol,
                    effective_from=effective_from,
                    effective_to=None,
                    source_file=source_file,
                    source_row=index,
                    source_key=source_key,
                    import_batch_id=import_batch_id,
                )
            )
            inserted += 1
    session.flush()
    return inserted
