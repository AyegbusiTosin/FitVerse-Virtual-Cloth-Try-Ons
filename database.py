"""
FitVerse — Database Connection & Session Management

Provides the SQLAlchemy 2.0 engine, session factory, declarative base,
and FastAPI dependency for scoped per-request database sessions.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import settings


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # Verifies connections before checkout to avoid stale drops
    echo=(settings.environment == "development"),
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""


def get_db() -> Generator[Session, None, None]:
    """
    Yield a database session per request and guarantee cleanup.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()