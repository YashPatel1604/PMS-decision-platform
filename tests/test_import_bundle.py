"""Phase 8 migration bundle import and verification tests."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from pms_platform.db.base import Base
from pms_platform.models.client_book_settings import ClientBookSettings
from pms_platform.models.client_position import ClientPosition
from pms_platform.models.nse_bhav import NseBhavBar, PivotPortfolioSymbol
from pms_platform.reconciliation.bundle import build_migration_bundle
from pms_platform.reconciliation.copy_bhav import copy_bhav_bars
from pms_platform.reconciliation.cutover import run_cutover_reconciliation
from pms_platform.reconciliation.import_bundle import import_migration_bundle
from pms_platform.reconciliation.verify import verify_rehearsal_import


def _twin_sessions():
    engines = [create_engine("sqlite+pysqlite:///:memory:") for _ in range(2)]
    factories = []
    for engine in engines:
        Base.metadata.create_all(engine)
        factories.append(sessionmaker(bind=engine, autoflush=False, autocommit=False))
    return factories[0](), factories[1]()


def test_import_bundle_round_trip(tmp_path: Path) -> None:
    samir, julesh = _twin_sessions()
    try:
        samir.add(
            ClientPosition(
                book="client",
                symbol="TCS",
                qty=Decimal("50"),
                mcap_factor=Decimal("1"),
                index_label="Nifty",
                row_version=1,
            )
        )
        samir.add(ClientBookSettings(book="sca", bank_balance=Decimal("100000"), row_version=1))
        julesh.add(
            ClientPosition(
                book="client",
                symbol="TCS",
                qty=Decimal("50"),
                mcap_factor=Decimal("1"),
                index_label="Nifty",
                row_version=1,
            )
        )
        julesh.add(ClientBookSettings(book="sca", bank_balance=Decimal("100000"), row_version=1))
        samir.add(PivotPortfolioSymbol(symbol="AAA", sort_order=1))
        julesh.add(PivotPortfolioSymbol(symbol="AAA", sort_order=1))
        samir.commit()
        julesh.commit()

        report = run_cutover_reconciliation(samir, julesh)
        bundle = build_migration_bundle(report, samir, julesh)
        bundle_path = tmp_path / "migration_bundle.json"
        bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

        target_engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(target_engine)
        TargetSession = sessionmaker(bind=target_engine)
        target = TargetSession()
        try:
            import_migration_bundle(target, bundle_path)
            target.commit()
            verification = verify_rehearsal_import(target, bundle_path)
            assert verification.passed
            pos = target.scalar(
                select(ClientPosition).where(
                    ClientPosition.book == "client",
                    ClientPosition.symbol == "TCS",
                )
            )
            assert pos is not None
            assert pos.qty == Decimal("50")
        finally:
            target.close()
            target_engine.dispose()
    finally:
        samir.close()
        julesh.close()


def test_copy_bhav_bars(tmp_path: Path) -> None:
    del tmp_path
    source_engine = create_engine("sqlite+pysqlite:///:memory:")
    target_engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(source_engine)
    Base.metadata.create_all(target_engine)
    Source = sessionmaker(bind=source_engine)()
    Target = sessionmaker(bind=target_engine)()
    try:
        Source.add(
            NseBhavBar(
                trade_date=date(2024, 1, 2),
                symbol="RELIANCE",
                series="EQ",
                open=Decimal("1"),
                high=Decimal("2"),
                low=Decimal("1"),
                close=Decimal("1.5"),
                volume=100,
                source_key="k1",
            )
        )
        Source.commit()
        result = copy_bhav_bars(Source, Target)
        Target.commit()
        assert result.inserted == 1
        assert result.source_count == 1
        result2 = copy_bhav_bars(Source, Target)
        assert result2.inserted == 0
        assert result2.skipped_existing == 1
    finally:
        Source.close()
        Target.close()
        source_engine.dispose()
        target_engine.dispose()
