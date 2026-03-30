import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add root directory to Python path so backend and scripts modules can be found
sys.path.insert(0, str(Path(__file__).parent.parent))

import backend
from backend import create_app
from scripts.init_d2ba_db import init_d2ba_db


@pytest.fixture(autouse=True)
def reset_app_singleton():
    """Reset the Flask app singleton before and after each test to prevent state pollution.

    This ensures that tests which call create_app() without parameters
    don't contaminate the global _app cache used by other tests.
    """
    backend._app = None
    yield
    backend._app = None


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
    patcher = patch("backend.pro_players.fetch_pro_players_from_api")
    mock_fetch = patcher.start()
    mock_fetch.side_effect = ConnectionError("Mocked connection error to skip startup sync")

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

    patcher.stop()

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
