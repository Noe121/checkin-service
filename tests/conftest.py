"""
Check-in Service - Test Configuration
Shared fixtures and configuration for tests
"""
import pytest
import sys
import os

# Add src to path for runtime imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def pytest_configure(config):
    """Configure pytest"""
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test"
    )

