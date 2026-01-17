import os
import threading

from flask import Flask

__version__ = "0.4"

# Module-level singleton and a lock to make creation thread-safe
_app = None
_app_lock = threading.Lock()


def create_app(test_config=None):
    """Create and configure the Flask application.

    In production mode (test_config=None), returns a singleton instance.
    In test mode, creates a new instance with test configuration.

    Args:
        test_config: Optional dictionary with test configuration.

    Returns:
        Configured Flask application instance.
    """
    global _app

    # Return cached instance for production
    if test_config is None and _app is not None:
        return _app

    app = Flask(__name__, instance_relative_config=True)

    # Configure app
    _configure_app(app, test_config)
    _init_extensions(app)

    # Cache singleton for production
    if test_config is None:
        with _app_lock:
            if _app is None:
                _app = app
            return _app

    return app


def _configure_app(app, test_config=None):
    """Configure Flask application with defaults and environment-specific settings."""
    # Print version once for production
    if test_config is None:
        print(f"Starting Dota Bet Analyzer v{__version__}")

    # Default configuration
    app.config.from_mapping(
        SECRET_KEY="dev",
        DATABASE_FILENAME="opendota.sqlite",
    )

    # Load environment-aware config
    app.config.from_object("backend.config.Config")

    # Load instance-specific or test config
    if test_config is None:
        app.config.from_pyfile("config.py", silent=True)
    else:
        app.config.from_mapping(test_config)

    # Setup database path
    os.makedirs(app.instance_path, exist_ok=True)
    db_filename = app.config.get("DATABASE_FILENAME", "opendota.sqlite")
    app.config["DATABASE"] = os.path.join(app.instance_path, db_filename)


def _init_extensions(app):
    """Initialize Flask extensions and register blueprints."""
    # Initialize database
    from . import db

    db.init_app(app)

    # Initialize d2ba database
    from .pro_players import init_d2ba_app, sync_pro_players_on_startup

    init_d2ba_app(app)

    # Register blueprints
    from .dota_bet_analyzer import bp as dota_bp
    from .dota_bet_analyzer import celery as celery_app

    app.register_blueprint(dota_bp)
    celery_app.conf.update(app.config or {})

    # Sync pro players on app startup (only in production, not in test mode)
    if app.config.get("TESTING") is not True:
        sync_pro_players_on_startup(app)
