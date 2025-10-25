"""
Admin Dashboard Service - Test Configuration
Shared fixtures and configuration for tests
"""
import pytest
import sys
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from models import Base


@pytest.fixture(scope="session")
def test_db_engine():
    """Create in-memory database for all tests"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        echo=False
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture(scope="function")
def test_db_session(test_db_engine):
    """Create a new database session for each test"""
    connection = test_db_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(autouse=True)
def reset_db(test_db_session):
    """Reset database before each test"""
    yield
    test_db_session.rollback()


def pytest_configure(config):
    """Configure pytest"""
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test"
    )
