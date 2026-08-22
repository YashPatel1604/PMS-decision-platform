"""Tests for evidence-based history gap classification."""

from __future__ import annotations

from pms_platform.models import ImportBatch, Security
from pms_platform.models.watchlist import Watchlist, WatchlistMember
from pms_platform.watchlists import identity_aliases as ia
from pms_platform.watchlists.history_audit import classify_member_history, summarize_history_classifications


def test_no_alias_classification_without_verified_rename(session, import_batch: ImportBatch) -> None:
    sec = Security(
        security_id="SEC100",
        portfolio_name="Regular Co",
        current_nse_symbol="REGCO",
        bse_code="500100",
        isin="INE100A01010",
        import_batch_id=import_batch.import_batch_id,
    )
    session.add(sec)
    wl = Watchlist(name="Test", is_default=False)
    session.add(wl)
    session.flush()
    member = WatchlistMember(
        watchlist_id=wl.watchlist_id,
        display_name="Regular Co",
        nse_symbol="REGCO",
        bse_code="500100",
        security_id=sec.security_id,
        resolution_status="RESOLVED",
    )
    session.add(member)
    session.flush()

    report = classify_member_history(session, member)
    assert report.cagr_5y_classification != "HISTORICAL_ALIAS_NOT_INGESTED"
    assert report.cagr_5y_classification in {
        "CURRENT_SYMBOL_HISTORY_NOT_INGESTED",
        "BSE_HISTORY_NOT_INGESTED",
        "NO_HISTORICAL_FILINGS_FOUND",
        None,
    }


def test_renamed_member_can_classify_alias_when_evidence_exists(
    session, import_batch: ImportBatch
) -> None:
    ia.bootstrap_identity_aliases(session)
    sec = session.scalar(
        __import__("sqlalchemy").select(Security).where(Security.bse_code == "517271")
    )
    assert sec is not None
    wl = Watchlist(name="Alias", is_default=False)
    session.add(wl)
    session.flush()
    member = WatchlistMember(
        watchlist_id=wl.watchlist_id,
        display_name="HBL Power",
        nse_symbol="HBLENGINE",
        bse_code="517271",
        security_id=sec.security_id,
        resolution_status="RESOLVED",
    )
    session.add(member)
    session.flush()

    report = classify_member_history(session, member)
    assert "HBL" in " ".join(report.verified_historical_aliases) or report.verified_historical_aliases


def test_summarize_does_not_over_classify_alias(session, import_batch: ImportBatch) -> None:
    ia.bootstrap_identity_aliases(session)
    wl = Watchlist(name="All", is_default=False)
    session.add(wl)
    session.flush()
    for name, bse, nse in (
        ("Regular", "500100", "REGCO"),
        ("HBL Power", "517271", "HBLENGINE"),
    ):
        sec = Security(
            security_id=f"SEC{bse}",
            portfolio_name=name,
            current_nse_symbol=nse,
            bse_code=bse,
            import_batch_id=import_batch.import_batch_id,
        )
        session.add(sec)
        session.flush()
        session.add(
            WatchlistMember(
                watchlist_id=wl.watchlist_id,
                display_name=name,
                nse_symbol=nse,
                bse_code=bse,
                security_id=sec.security_id,
                resolution_status="RESOLVED",
            )
        )
    session.flush()
    members = list(
        session.scalars(
            __import__("sqlalchemy").select(WatchlistMember).where(
                WatchlistMember.watchlist_id == wl.watchlist_id
            )
        ).all()
    )
    summary = summarize_history_classifications(session, members)
    alias_count = summary["cagr_5y"].get("HISTORICAL_ALIAS_NOT_INGESTED", 0)
    assert alias_count <= 1
