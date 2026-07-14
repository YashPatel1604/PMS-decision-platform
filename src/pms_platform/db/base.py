"""SQLAlchemy engine and declarative base."""

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from pms_platform.config import settings


class Base(DeclarativeBase):
    """Declarative base for ORM models."""


@lru_cache
def get_engine():
    """Return a cached SQLAlchemy engine."""
    return create_engine(settings.database_url, pool_pre_ping=True)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    """Return a cached session factory."""
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)


def get_session() -> Generator[Session, None, None]:
    """Yield a database session."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
