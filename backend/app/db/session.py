"""SQLAlchemy engine and session factory for the Main Database.

The schema itself is ON-11; this module only establishes the connection the
rest of the backend uses.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all Main Database models."""


_settings = get_settings()

engine = create_engine(_settings.database_url, pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """Yield a database session, closing it afterwards.

    Used as a FastAPI dependency.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def check_connection() -> bool:
    """Return True if the Main Database answers a trivial query."""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return True
