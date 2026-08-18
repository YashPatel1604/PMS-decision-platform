"""Pytest configuration and shared fixtures."""

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from pms_platform.config import settings
from pms_platform.db.base import Base
from pms_platform.models import ImportBatch, Security


@pytest.fixture(autouse=True)
def _default_auth_disabled_for_legacy_api_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep existing smoke tests working without cookies unless a test opts in."""
    monkeypatch.setattr(settings, "auth_disabled", True)


@pytest.fixture
def session() -> Generator[Session, None, None]:
    """Provide an isolated in-memory database session."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = factory()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def import_batch(session: Session) -> ImportBatch:
    """Create a test import batch."""
    batch = ImportBatch(
        source_type="test",
        source_file="test.xlsx",
        source_checksum="test-checksum",
        status="completed",
    )
    session.add(batch)
    session.flush()
    return batch


@pytest.fixture
def sample_security(session: Session, import_batch: ImportBatch) -> Security:
    """Create a sample security."""
    security = Security(
        security_id="SEC999",
        portfolio_name="TestCo",
        canonical_name="Test Company Limited",
        import_batch_id=import_batch.import_batch_id,
    )
    session.add(security)
    session.flush()
    return security
