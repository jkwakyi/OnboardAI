"""SQLAlchemy engine and session factory for the Main Database.

The tables themselves live in `app.db.models`; this module establishes the
connection and the declarative base they share.
"""

from collections.abc import Iterator

from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

# Alembic compares the database against these models to decide what a
# migration should do, and it can only match a constraint it can name. Left
# to the database, a check or a foreign key gets an arbitrary name that
# differs between PostgreSQL and the SQLite used in the unit tests, and the
# comparison then reports spurious changes.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for all Main Database models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


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
