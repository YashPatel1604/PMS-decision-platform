"""Alembic migration smoke tests for watchlist schema."""

from __future__ import annotations

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from pms_platform.db.base import Base
from pms_platform.models import (  # noqa: F401
    CompanyFundamentalsQuarterly,
    FundamentalSnapshot,
    Watchlist,
    WatchlistAlert,
    WatchlistMember,
    WatchlistRefreshLock,
    WatchlistResolutionLog,
)


def test_watchlist_orm_tables_create_on_fresh_database() -> None:
    """Fresh install: watchlist ORM metadata creates expected tables."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    tables = set(inspect(engine).get_table_names())
    expected = {
        "watchlists",
        "watchlist_members",
        "watchlist_resolution_logs",
        "watchlist_alerts",
        "watchlist_refresh_locks",
        "company_fundamentals_quarterly",
        "fundamental_snapshots",
    }
    missing = expected - tables
    assert not missing, f"Missing tables: {sorted(missing)}"


def test_watchlist_migrations_are_chained_to_head() -> None:
    """Upgrade path: watchlist migrations link d0 → … → current head."""
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    head = script.get_current_head()
    assert head == "d7e8f0a1b2c3"

    watchlist_chain = [
        "d0e1f2a3b4c5",
        "e1f2a3b4c5d6",
        "f2a3b4c5d6e7",
        "g3b4c5d6e7f8",
        "h4c5d6e7f8a9",
    ]
    for revision_id in watchlist_chain:
        rev = script.get_revision(revision_id)
        assert rev is not None, revision_id

    refresh_lock = script.get_revision("h4c5d6e7f8a9")
    assert refresh_lock.down_revision == "g3b4c5d6e7f8"
    fundamentals = script.get_revision("f2a3b4c5d6e7")
    assert fundamentals.down_revision == "e1f2a3b4c5d6"
