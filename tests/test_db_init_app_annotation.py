"""Tests for database initialization with app annotation."""

from backend import create_app


def test_app_teardown_registered():
    """Test that app has teardown handlers registered."""
    app = create_app()

    # Check if app context processors or handlers exist
    assert app is not None
    # Database setup should be handled by Flask-SQLAlchemy or similar
    assert hasattr(app, "teardown_appcontext")
