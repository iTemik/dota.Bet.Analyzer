"""Pytest configuration and shared fixtures for all tests.

Test Data Isolation Strategy:
- Each test gets its own temporary database (separate file/memory)
- Uses Flask's test_client for complete request isolation
- Database connections are closed after each test
- Temporary files are cleaned up automatically

Best practices implemented:
1. Separate test database per test (no production data contamination)
2. Automatic cleanup of temp directories
3. Mocked external API calls to prevent real network requests
4. Test database initialized with schema on every test
"""

import os
import shutil
import tempfile
from unittest.mock import patch

import pytest

from backend import create_app
from scripts.init_d2ba_db import init_d2ba_db


@pytest.fixture
def app():
    """Create application for testing with isolated test database.

    This fixture:
    - Creates temporary directories for both main and d2ba databases
    - Initializes a clean database schema
    - Mocks external API calls
    - Cleans up all temporary files after test

    Returns:
        Flask app configured for testing
    """
    # Create temporary database directories with unique path for each test
    temp_dir = tempfile.mkdtemp()
    custom_instance = tempfile.mkdtemp()

    # Patch the API call to prevent real requests during app startup
    with patch("backend.pro_players.fetch_pro_players_from_api") as mock_fetch:
        mock_fetch.return_value = None  # Return None to skip startup sync

        app = create_app(
            {
                "TESTING": True,
                "DATABASE": os.path.join(temp_dir, "opendota.sqlite"),
            }
        )

        # Override instance path for d2ba database
        app.instance_path = custom_instance

        # Initialize d2ba database in custom instance path
        d2ba_path = os.path.join(custom_instance, "d2ba.sqlite")
        init_d2ba_db(d2ba_path)

    yield app

    # Cleanup: Remove temporary directories
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    if os.path.exists(custom_instance):
        shutil.rmtree(custom_instance)


@pytest.fixture
def client(app):
    """Create test client for making requests to the app.

    Returns:
        Flask test client
    """
    return app.test_client()
