"""SQLAlchemy engine and declarative base."""

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from pms_platform.config import settings


class Base(DeclarativeBase):
    """Declarative base for ORM models."""


@lru_cache
def get_migration_engine():
    """Engine for Alembic and controlled schema migrations."""
    return create_engine(settings.migration_database_url, pool_pre_ping=True)


@lru_cache
def get_engine():
    """Return a cached SQLAlchemy engine."""
    return create_engine(settings.database_url, pool_pre_ping=True)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    """Return a cached session factory."""
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
