"""Deterministic financial discovery identities for one security."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.models import Security
from pms_platform.models.security_identity_alias import SecurityIdentityAlias


@dataclass(frozen=True)
class DiscoveryIdentity:
    value: str
    identity_type: str
    valid_from: date | None
    valid_to: date | None
    relationship: str
    source: str


@dataclass(frozen=True)
class FinancialDiscoveryIdentitySet:
    security_id: str
    canonical_name: str | None
    current_nse_symbol: str | None
    current_bse_code: str | None
    current_isin: str | None
    historical_nse_symbols: tuple[str, ...]
    historical_bse_codes: tuple[str, ...]
    historical_isins: tuple[str, ...]
    historical_names: tuple[str, ...]
    identities: tuple[DiscoveryIdentity, ...]

    def all_identities(self) -> tuple[DiscoveryIdentity, ...]:
        return self.identities

    def nse_symbols_for_discovery(self) -> tuple[str, ...]:
        """Current symbol first, then verified historical symbols."""
        out: list[str] = []
        if self.current_nse_symbol:
            out.append(self.current_nse_symbol)
        for sym in self.historical_nse_symbols:
            if sym not in out:
                out.append(sym)
        return tuple(out)

    def bse_codes_for_discovery(self) -> tuple[str, ...]:
        out: list[str] = []
        if self.current_bse_code:
            out.append(self.current_bse_code)
        for code in self.historical_bse_codes:
            if code not in out:
                out.append(code)
        return tuple(out)


def build_financial_discovery_identities(
    session: Session,
    security_id: str,
) -> FinancialDiscoveryIdentitySet | None:
    sec = session.get(Security, security_id)
    if sec is None:
        return None

    identities: list[DiscoveryIdentity] = []
    current_nse = (sec.current_nse_symbol or "").strip().upper() or None
    current_bse = (sec.bse_code or "").strip() or None
    current_isin = (sec.isin or "").strip().upper() or None

    if current_nse:
        identities.append(
            DiscoveryIdentity(
                value=current_nse,
                identity_type="NSE_SYMBOL",
                valid_from=None,
                valid_to=None,
                relationship="CURRENT",
                source="securities",
            )
        )
    if current_bse:
        identities.append(
            DiscoveryIdentity(
                value=current_bse,
                identity_type="BSE_CODE",
                valid_from=None,
                valid_to=None,
                relationship="CURRENT",
                source="securities",
            )
        )
    if current_isin:
        identities.append(
            DiscoveryIdentity(
                value=current_isin,
                identity_type="ISIN",
                valid_from=None,
                valid_to=None,
                relationship="CURRENT",
                source="securities",
            )
        )

    hist_nse: list[str] = []
    hist_bse: list[str] = []
    hist_isin: list[str] = []
    hist_names: list[str] = []

    alias_rows = session.scalars(
        select(SecurityIdentityAlias).where(SecurityIdentityAlias.security_id == security_id)
    ).all()
    for row in alias_rows:
        rel = row.relationship_type or "ALIAS"
        if row.alias_type == "NSE_SYMBOL" and row.alias_value:
            val = row.alias_value.strip().upper()
            if val and val != current_nse:
                hist_nse.append(val)
                identities.append(
                    DiscoveryIdentity(
                        value=val,
                        identity_type="NSE_SYMBOL",
                        valid_from=row.effective_from,
                        valid_to=row.effective_to,
                        relationship=rel,
                        source=row.source,
                    )
                )
        if row.alias_type == "BSE_CODE" and row.alias_value:
            val = row.alias_value.strip()
            if val and val != current_bse:
                hist_bse.append(val)
                identities.append(
                    DiscoveryIdentity(
                        value=val,
                        identity_type="BSE_CODE",
                        valid_from=row.effective_from,
                        valid_to=row.effective_to,
                        relationship=rel,
                        source=row.source,
                    )
                )
        if row.historical_nse_symbol:
            val = row.historical_nse_symbol.strip().upper()
            if val and val != current_nse and val not in hist_nse:
                hist_nse.append(val)
        if row.historical_bse_code:
            val = row.historical_bse_code.strip()
            if val and val != current_bse and val not in hist_bse:
                hist_bse.append(val)
        if row.historical_isin:
            val = row.historical_isin.strip().upper()
            if val and val != current_isin:
                hist_isin.append(val)
        if row.alias_name and row.alias_type == "WATCHLIST_NAME":
            hist_names.append(row.alias_name)

    if sec.historical_nse_symbol:
        val = sec.historical_nse_symbol.strip().upper()
        if val and val != current_nse and val not in hist_nse:
            hist_nse.append(val)

    return FinancialDiscoveryIdentitySet(
        security_id=security_id,
        canonical_name=sec.canonical_name,
        current_nse_symbol=current_nse,
        current_bse_code=current_bse,
        current_isin=current_isin,
        historical_nse_symbols=tuple(hist_nse),
        historical_bse_codes=tuple(hist_bse),
        historical_isins=tuple(hist_isin),
        historical_names=tuple(hist_names),
        identities=tuple(identities),
    )
