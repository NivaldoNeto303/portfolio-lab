"""Shared test fixtures.

The app is wired to a single module-level SQLite engine. For tests we override
that engine with an in-memory database and override the FastAPI session
dependency so nothing touches the real ``portfolio_lab.db`` file.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app import db, main


@pytest.fixture(name="session")
def session_fixture():
    # StaticPool keeps the single in-memory DB alive across connections.
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session):
    def get_session_override():
        yield session

    main.app.dependency_overrides[db.get_session] = get_session_override
    client = TestClient(main.app)
    yield client
    main.app.dependency_overrides.clear()
