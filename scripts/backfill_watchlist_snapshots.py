"""Backfill missing valuation/fundamentals for every watchlist member.

Usage:
  uv run python scripts/backfill_watchlist_snapshots.py
  # or inside api container:
  python scripts/backfill_watchlist_snapshots.py
"""

from __future__ import annotations

from pms_platform.db import get_session_factory
from pms_platform.watchlists import service as wl
from pms_platform.watchlists.metrics_cache import rebuild_watchlist_metrics
from pms_platform.watchlists.refresh import (
    _watchlist_bse_codes,
    codes_missing_valuation,
    enrich_watchlist_for_codes,
)


def main() -> None:
    Session = get_session_factory()
    with Session() as session:
        for watchlist in wl.list_watchlists(session):
            codes = _watchlist_bse_codes(session, watchlist.watchlist_id)
            missing = codes_missing_valuation(session, codes)
            print(
                f"{watchlist.name}: {len(missing)}/{len(codes)} missing valuation",
                flush=True,
            )
            for i, code in enumerate(missing, start=1):
                print(f"  [{i}/{len(missing)}] {code}", flush=True)
                try:
                    enrich_watchlist_for_codes(session, watchlist.watchlist_id, [code])
                    session.commit()
                except Exception as exc:
                    session.rollback()
                    print(f"  FAIL {code}: {exc}", flush=True)
            rebuild_watchlist_metrics(session, watchlist.watchlist_id)
            session.commit()
            print(f"DONE {watchlist.name}", flush=True)
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    main()
