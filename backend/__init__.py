import os
import threading

from flask import Flask

__version__ = "0.1"

# Module-level singleton and a lock to make creation thread-safe
_app = None
_app_lock = threading.Lock()


def create_app(test_config=None):
    global _app

    # If not in test mode and an instance already exists, return it (singleton)
    if test_config is None and _app is not None:
        return _app

    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY="dev",
        DATABASE_FILENAME="dba.sqlite",
    )

    # Load configuration defaults from backend.config.Config (env-aware)
    try:
        app.config.from_object("backend.config.Config")
    except Exception:
        # If the config object can't be loaded, continue with defaults
        pass

    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile("config.py", silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    # Ensure DATABASE is constructed from configurable filename (DATABASE_FILENAME)
    db_filename = app.config.get("DATABASE_FILENAME", "dba.sqlite")
    app.config["DATABASE"] = os.path.join(app.instance_path, db_filename)

    # a simple page that says hello
    @app.route("/hello")
    def hello():
        return "Hello, World!"

    from . import db

    # Call init_app if the db module provides it (optional)
    if hasattr(db, "init_app"):
        db.init_app(app)

    # Register blueprints and configure other extensions here to avoid circular imports
    try:
        from .dota_bet_analyzer import bp as dota_bp
        from .dota_bet_analyzer import celery as celery_app

        app.register_blueprint(dota_bp)
        # Update celery configuration from app config if available
        celery_app.conf.update(app.config or {})
    except Exception:
        # Import errors are acceptable here (e.g., during some tests),
        # but we don't want to crash app creation because of it.
        pass

    if test_config is None:
        with _app_lock:
            if _app is None:
                _app = app
            # Always return the module-level singleton in non-test mode
            return _app

    return app
