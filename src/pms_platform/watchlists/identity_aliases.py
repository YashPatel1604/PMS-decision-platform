"""Historical identity aliases: seed data, lookup, bootstrap."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.models import ImportBatch, Security
from pms_platform.models.security_identity_alias import SecurityIdentityAlias

# Verified successor/rename mappings (exchange codes from BSE ListOfScrip / NSE).
# ponytail: seed file, not live discovery — CI uses this deterministic set.
VERIFIED_IDENTITY_MAPPINGS: tuple[dict[str, str], ...] = (
    {
        "watchlist_name": "HBL Power",
        "relationship_type": "RENAMED",
        "current_name": "HBL Engineering Ltd",
        "bse_code": "517271",
        "nse_symbol": "HBLENGINE",
        "historical_nse_symbol": "HBLPOWER",
        "historical_bse_code": "517081",
        "isin": "INE292B01021",
        "historical_name": "HBL Power Systems Ltd",
        "notes": "Renamed to HBL Engineering; legacy BSE 517081",
    },
    {
        "watchlist_name": "Sequent",
        "relationship_type": "RENAMED",
        "current_name": "Viyash Scientific Ltd",
        "bse_code": "512529",
        "nse_symbol": "VIYASH",
        "historical_nse_symbol": "SEQUENT",
        "isin": "INE807F01027",
        "historical_name": "Sequent Scientific Ltd",
        "notes": "Renamed to Viyash Scientific",
    },
    {
        "watchlist_name": "Allsec Tech",
        "relationship_type": "RENAMED",
        "current_name": "Alldigi Tech Ltd",
        "bse_code": "532633",
        "nse_symbol": "ALLDIGI",
        "historical_nse_symbol": "ALLSEC",
        "isin": "INE835G01018",
        "historical_name": "Allsec Technologies Ltd",
        "notes": "Renamed to Alldigi Tech",
    },
    {
        "watchlist_name": "ITD Cement",
        "relationship_type": "RENAMED",
        "current_name": "Cemindia Projects Ltd",
        "bse_code": "509496",
        "nse_symbol": "CEMPRO",
        "historical_nse_symbol": "ITDCEM",
        "isin": "INE686A01026",
        "historical_name": "ITD Cementation India Ltd",
        "notes": "Renamed to Cemindia Projects; NSE CEMPRO",
    },
    {
        "watchlist_name": "EPC Industrie",
        "relationship_type": "RENAMED",
        "current_name": "Mahindra EPC Irrigation Ltd",
        "bse_code": "523754",
        "nse_symbol": "MAHEPC",
        "historical_nse_symbol": "EPCIND",
        "isin": "INE215D01010",
        "historical_name": "EPC Industrie Ltd",
        "notes": "Renamed to Mahindra EPC Irrigation",
    },
    {
        "watchlist_name": "SQS BFSI",
        "relationship_type": "RENAMED",
        "current_name": "Expleo Solutions Ltd",
        "bse_code": "533121",
        "nse_symbol": "EXPLEOSOL",
        "historical_nse_symbol": "SQSBFSI",
        "isin": "INE201K01015",
        "historical_name": "SQS India BFSI Ltd",
        "notes": "Renamed to Expleo Solutions",
    },
    {
        "watchlist_name": "Eros Media",
        "relationship_type": "ACTIVE_SAME_SECURITY",
        "current_name": "Eros International Media Ltd",
        "bse_code": "533261",
        "nse_symbol": "EROSMEDIA",
        "isin": "INE416L01017",
        "historical_name": "Eros International Media Ltd",
        "notes": "Still listed; abbreviated watchlist seed name",
    },
)

# Positive unsupported classifications only.
POSITIVE_UNSUPPORTED: dict[str, str] = {
    "Dummy": "DUMMY",
    "DFM Foods": "ACQUIRED_AND_DELISTED",
    "Majesco": "ACQUIRED_AND_DELISTED",
    "Manpasand": "DELISTED_NO_SUCCESSOR",
}


@dataclass(frozen=True)
class AliasMatch:
    security_id: str | None
    bse_code: str | None
    nse_symbol: str | None
    isin: str | None
    current_name: str | None
    relationship_type: str
    match_method: str
    notes: str | None = None


@dataclass(frozen=True)
class AliasDiscoveryTarget:
    watchlist_name: str
    security_id: str
    canonical_bse: str
    canonical_nse: str | None
    historical_nse: str | None
    historical_bse: str | None


def historical_discovery_targets(session: Session) -> list[AliasDiscoveryTarget]:
    """Verified RENAMED aliases with distinct pre-rename exchange identifiers."""
    from pms_platform.models import Security

    out: list[AliasDiscoveryTarget] = []
    for spec in VERIFIED_IDENTITY_MAPPINGS:
        if spec["relationship_type"] != "RENAMED":
            continue
        hist_nse = (spec.get("historical_nse_symbol") or "").strip().upper() or None
        hist_bse = (spec.get("historical_bse_code") or "").strip() or None
        canon_nse = (spec.get("nse_symbol") or "").strip().upper() or None
        canon_bse = spec["bse_code"]
        if hist_nse == canon_nse and (not hist_bse or hist_bse == canon_bse):
            continue
        sec = session.scalar(select(Security).where(Security.bse_code == canon_bse))
        if sec is None:
            continue
        out.append(
            AliasDiscoveryTarget(
                watchlist_name=spec["watchlist_name"],
                security_id=sec.security_id,
                canonical_bse=canon_bse,
                canonical_nse=canon_nse,
                historical_nse=hist_nse if hist_nse != canon_nse else None,
                historical_bse=hist_bse if hist_bse and hist_bse != canon_bse else None,
            )
        )
    return out


def lookup_watchlist_alias(session: Session, display_name: str) -> AliasMatch | None:
    """Find a verified alias by exact watchlist display name."""
    key = display_name.strip()
    if not key:
        return None
    row = session.scalar(
        select(SecurityIdentityAlias)
        .where(
            SecurityIdentityAlias.alias_type == "WATCHLIST_NAME",
            SecurityIdentityAlias.alias_value == key,
        )
        .limit(1)
    )
    if row is None:
        for spec in VERIFIED_IDENTITY_MAPPINGS:
            if spec["watchlist_name"] == key:
                return AliasMatch(
                    security_id=None,
                    bse_code=spec["bse_code"],
                    nse_symbol=spec["nse_symbol"],
                    isin=spec["isin"],
                    current_name=spec["current_name"],
                    relationship_type=spec["relationship_type"],
                    match_method="SEED",
                    notes=spec.get("notes"),
                )
        return None
    sec = session.get(Security, row.security_id)
    return AliasMatch(
        security_id=row.security_id,
        bse_code=sec.bse_code if sec else row.historical_bse_code,
        nse_symbol=sec.current_nse_symbol if sec else row.historical_nse_symbol,
        isin=sec.isin if sec else row.historical_isin,
        current_name=sec.canonical_name if sec else row.alias_name,
        relationship_type=row.relationship_type,
        match_method="ALIAS",
        notes=row.notes,
    )


def lookup_symbol_alias(
    session: Session,
    *,
    nse: str | None = None,
    bse: str | None = None,
    isin: str | None = None,
) -> AliasMatch | None:
    """Resolve historical exchange identifiers to canonical security."""
    for alias_type, value in (
        ("ISIN", isin),
        ("BSE_CODE", bse),
        ("NSE_SYMBOL", nse),
    ):
        if not value:
            continue
        normalized = value.strip().upper() if alias_type == "ISIN" else value.strip()
        row = session.scalar(
            select(SecurityIdentityAlias)
            .where(
                SecurityIdentityAlias.alias_type == alias_type,
                SecurityIdentityAlias.alias_value == normalized,
            )
            .limit(1)
        )
        if row is None:
            continue
        sec = session.get(Security, row.security_id)
        return AliasMatch(
            security_id=row.security_id,
            bse_code=sec.bse_code if sec else None,
            nse_symbol=sec.current_nse_symbol if sec else None,
            isin=sec.isin if sec else None,
            current_name=sec.canonical_name if sec else row.alias_name,
            relationship_type=row.relationship_type,
            match_method=f"HISTORICAL_{alias_type}",
            notes=row.notes,
        )
    return None


def all_identifiers_for_security(session: Session, security_id: str) -> list[tuple[str, str]]:
    """Return all (type, value) identifiers for financial discovery."""
    sec = session.get(Security, security_id)
    if sec is None:
        return []
    out: list[tuple[str, str]] = []
    if sec.current_nse_symbol:
        out.append(("NSE_SYMBOL", sec.current_nse_symbol))
    if sec.historical_nse_symbol:
        out.append(("NSE_SYMBOL", sec.historical_nse_symbol))
    if sec.bse_code:
        out.append(("BSE_CODE", sec.bse_code))
    if sec.isin:
        out.append(("ISIN", sec.isin))
    for row in session.scalars(
        select(SecurityIdentityAlias).where(SecurityIdentityAlias.security_id == security_id)
    ).all():
        if row.alias_type in {"NSE_SYMBOL", "BSE_CODE", "ISIN"}:
            out.append((row.alias_type, row.alias_value))
    seen: set[tuple[str, str]] = set()
    deduped: list[tuple[str, str]] = []
    for item in out:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def bootstrap_identity_aliases(session: Session) -> int:
    """Idempotently seed verified alias rows and ensure target securities exist."""
    from pms_platform.watchlists.identity_link import upsert_security_from_exchange

    batch = session.scalar(
        select(ImportBatch)
        .where(ImportBatch.source_type == "identity_aliases_seed")
        .order_by(ImportBatch.import_batch_id.desc())
        .limit(1)
    )
    if batch is None:
        batch = ImportBatch(
            source_type="identity_aliases_seed",
            source_file="identity_aliases_seed",
            source_checksum="identity_aliases_seed_v1",
            status="completed",
        )
        session.add(batch)
        session.flush()

    inserted = 0
    for spec in VERIFIED_IDENTITY_MAPPINGS:
        sec, _ = upsert_security_from_exchange(
            session,
            bse=spec["bse_code"],
            nse=spec["nse_symbol"],
            isin=spec["isin"],
            display_name=spec["current_name"],
            import_batch_id=batch.import_batch_id,
        )
        sec.canonical_name = spec["current_name"]
        pairs = [
            ("WATCHLIST_NAME", spec["watchlist_name"], spec["historical_name"]),
            ("NSE_SYMBOL", spec.get("nse_symbol", ""), None),
            ("BSE_CODE", spec["bse_code"], None),
            ("ISIN", spec["isin"], None),
        ]
        for alias_type, alias_value, alias_name in pairs:
            if not alias_value:
                continue
            existing = session.scalar(
                select(SecurityIdentityAlias).where(
                    SecurityIdentityAlias.alias_type == alias_type,
                    SecurityIdentityAlias.alias_value == alias_value,
                    SecurityIdentityAlias.relationship_type == spec["relationship_type"],
                )
            )
            if existing is not None:
                continue
            session.add(
                SecurityIdentityAlias(
                    security_id=sec.security_id,
                    alias_name=alias_name or spec["current_name"],
                    alias_type=alias_type,
                    alias_value=alias_value,
                    relationship_type=spec["relationship_type"],
                    historical_nse_symbol=spec.get("historical_nse_symbol") or spec.get("nse_symbol"),
                    historical_bse_code=spec.get("historical_bse_code") or spec["bse_code"],
                    historical_isin=spec.get("isin"),
                    effective_from=date(2012, 1, 1),
                    source="watchlist_seed",
                    notes=spec.get("notes"),
                )
            )
            inserted += 1
        hist_nse = (spec.get("historical_nse_symbol") or "").strip().upper()
        curr_nse = (spec.get("nse_symbol") or "").strip().upper()
        if hist_nse and hist_nse != curr_nse:
            existing = session.scalar(
                select(SecurityIdentityAlias).where(
                    SecurityIdentityAlias.alias_type == "NSE_SYMBOL",
                    SecurityIdentityAlias.alias_value == hist_nse,
                    SecurityIdentityAlias.relationship_type == spec["relationship_type"],
                )
            )
            if existing is None:
                session.add(
                    SecurityIdentityAlias(
                        security_id=sec.security_id,
                        alias_name=spec.get("historical_name"),
                        alias_type="NSE_SYMBOL",
                        alias_value=hist_nse,
                        relationship_type=spec["relationship_type"],
                        historical_nse_symbol=hist_nse,
                        historical_bse_code=spec.get("historical_bse_code") or spec["bse_code"],
                        historical_isin=spec.get("isin"),
                        effective_from=date(2012, 1, 1),
                        source="watchlist_seed",
                        notes=spec.get("notes"),
                    )
                )
                inserted += 1
        hist_bse = (spec.get("historical_bse_code") or "").strip()
        if hist_bse and hist_bse != spec["bse_code"]:
            existing = session.scalar(
                select(SecurityIdentityAlias).where(
                    SecurityIdentityAlias.alias_type == "BSE_CODE",
                    SecurityIdentityAlias.alias_value == hist_bse,
                    SecurityIdentityAlias.relationship_type == spec["relationship_type"],
                )
            )
            if existing is None:
                session.add(
                    SecurityIdentityAlias(
                        security_id=sec.security_id,
                        alias_name=spec.get("historical_name"),
                        alias_type="BSE_CODE",
                        alias_value=hist_bse,
                        relationship_type=spec["relationship_type"],
                        historical_nse_symbol=hist_nse or curr_nse,
                        historical_bse_code=hist_bse,
                        historical_isin=spec.get("isin"),
                        effective_from=date(2012, 1, 1),
                        source="watchlist_seed",
                        notes=spec.get("notes"),
                    )
                )
                inserted += 1
    session.flush()
    return inserted
