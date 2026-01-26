import os
import threading
from pathlib import Path

from flask import Flask

# Read version from VERSION file (single source of truth)
_version_file = Path(__file__).parent / "VERSION"
__version__ = _version_file.read_text().strip() if _version_file.exists() else "0.0"

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
        DATABASE_FILENAME="d2ba.sqlite",
        # OpenAPI/Swagger configuration
        API_TITLE="Dota Bet Analyzer API",
        API_VERSION=__version__,
        OPENAPI_VERSION="3.0.2",
        OPENAPI_URL_PREFIX="/api",
        OPENAPI_SWAGGER_UI_PATH="/swagger-ui",
        OPENAPI_SWAGGER_UI_URL="https://cdn.jsdelivr.net/npm/swagger-ui-dist/",
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
    db_filename = app.config.get("DATABASE_FILENAME", "d2ba.sqlite")
    app.config["DATABASE"] = os.path.join(app.instance_path, db_filename)


def _extract_error_from_dict(fields):
    """Extract error from dict structure (field -> errors mapping).

    Args:
        fields: Dict mapping field names to error lists or nested dicts

    Returns:
        Tuple of (field_name, error_message) or (None, None)
    """
    for field, errors in fields.items():
        if isinstance(errors, list) and errors:
            return field, errors[0]
        if isinstance(errors, dict):
            # Handle deeply nested errors like {"0": ["error"]}
            for _, sub_errors in errors.items():
                if isinstance(sub_errors, list) and sub_errors:
                    return field, sub_errors[0]
    return None, None


def _extract_first_error(original_errors):
    """Extract the first field name and error message from nested validation errors.

    Args:
        original_errors: Nested dict of validation errors

    Returns:
        Tuple of (field_name, error_message) or (None, None) if no errors found
    """
    # Handle nested errors structure (e.g., {"query": {"field": ["error"]}})
    for location, fields in original_errors.items():
        if isinstance(fields, dict):
            result = _extract_error_from_dict(fields)
            if result[0] is not None:
                return result
        elif isinstance(fields, list) and fields:
            return location, fields[0]

    return None, None


def _get_validation_errors(error):
    """Extract validation errors from error object.

    Args:
        error: Flask error object

    Returns:
        Dict of validation errors or empty dict
    """
    # flask-smorest/webargs stores validation errors in error.exc.messages
    if hasattr(error, "exc") and hasattr(error.exc, "messages"):
        return error.exc.messages
    # Fallback to error.data if exc.messages is not available
    if hasattr(error, "data") and isinstance(error.data, dict):
        return error.data.get("errors", {})
    return {}


def _register_validation_error_handler(app):
    """Register custom error handler for validation errors to match ErrorSchema format.

    Transforms flask-smorest/webargs validation errors (422) from the default format:
    {
        "code": 422,
        "errors": {"query": {"field": ["error message"]}},
        "status": "Unprocessable Entity"
    }

    To our unified ErrorSchema format:
    {
        "status": 422,
        "code": "VALIDATION_ERROR",
        "message": "Validation failed",
        "details": {"errors": {...}}
    }
    """
    from flask import jsonify, request
    from werkzeug.exceptions import UnprocessableEntity

    @app.errorhandler(422)
    @app.errorhandler(UnprocessableEntity)
    def handle_validation_error(error):
        """Handle 422 validation errors and transform them to ErrorSchema format."""
        original_errors = _get_validation_errors(error)

        # Format human-readable message from validation errors
        message = "Validation failed"
        if original_errors:
            first_field, first_error = _extract_first_error(original_errors)
            if first_field and first_error:
                message = f"Validation failed: {first_field} - {first_error}"

        # Transform to our ErrorSchema format
        response_data = {
            "status": 422,
            "code": "VALIDATION_ERROR",
            "message": message,
            "details": {"url": request.path, "errors": original_errors},
        }

        return jsonify(response_data), 422


def _init_extensions(app):
    """Initialize Flask extensions and register blueprints."""
    # Initialize flask-smorest API
    from flask_smorest import Api

    api = Api(app)

    # Register custom error handler for validation errors (422)
    # This transforms webargs/marshmallow validation errors to match our ErrorSchema format
    _register_validation_error_handler(app)

    # Initialize database
    from . import db

    db.init_app(app)

    # Initialize d2ba database
    from .pro_players import init_d2ba_app, sync_pro_players_on_startup

    init_d2ba_app(app)

    # Register blueprints
    from .dota_bet_analyzer import bp as dota_bp
    from .dota_bet_analyzer import celery as celery_app

    api.register_blueprint(dota_bp)
    celery_app.conf.update(app.config or {})

    # Sync pro players on app startup (only in production, not in test mode)
    if app.config.get("TESTING") is not True:
        sync_pro_players_on_startup(app)
