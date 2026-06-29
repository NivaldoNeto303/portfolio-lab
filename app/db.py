"""Database engine, session, and initialization.

SQLite is configured with ``check_same_thread=False`` because FastAPI may use
a different thread per request; SQLModel/SQLAlchemy manages the connection pool
safely on top of that.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

# Keep the DB file next to the project root, not the current working directory,
# so it lands in a predictable place regardless of where uvicorn is launched.
DB_PATH = Path(__file__).resolve().parent.parent / "portfolio_lab.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    """Create tables if they don't exist. Safe to call on every startup."""
    # Importing models registers them on SQLModel.metadata before create_all.
    from app import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency that yields a request-scoped session."""
    with Session(engine) as session:
        yield session
