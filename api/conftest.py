"""
Fixtures for Pytest tests.
"""
from unittest import mock

import pytest
from sqlalchemy.orm import Session

from api.db import postgres_engine
from api.test.common import test_db


@pytest.fixture
def test_session() -> Session:
    """
    Pytest Fixture to get a test database session.
    """
    test_engine, session = test_db()

    def fake_get_db_context():
        """Get the testing db"""
        return test_engine, session

    try:
        with mock.patch('api.db._get_db_session', fake_get_db_context):
            yield session
    finally:
        session.rollback()
        session.close()
        test_engine.dispose()
        conn = postgres_engine.connect()
        conn.execute(f'DROP DATABASE IF EXISTS {test_engine.engine.url.database}')
