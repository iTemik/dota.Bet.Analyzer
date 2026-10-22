"""Connection to predictions.sqlite: the user's own data (snapshots, predictions), kept apart from the d2ba cache."""

import os
import sqlite3
from typing import cast

from flask import Flask, current_app, g

PREDICTIONS_DB_FILENAME = "predictions.sqlite"


def get_predictions_db() -> sqlite3.Connection:
    """Get the request's connection to predictions.sqlite.

    Returns:
        Connection with rows as sqlite3.Row
    """
    if "predictions_db" not in g:
        db_path = os.path.join(current_app.instance_path, PREDICTIONS_DB_FILENAME)
        g.predictions_db = sqlite3.connect(db_path)
        g.predictions_db.row_factory = sqlite3.Row
        g.predictions_db.execute("PRAGMA foreign_keys = ON")
    return cast(sqlite3.Connection, g.predictions_db)


def close_predictions_db(e: BaseException | None = None) -> None:
    """Close the request's predictions.sqlite connection, if one was opened."""
    db = g.pop("predictions_db", None)
    if db is not None:
        db.close()


def init_predictions_app(app: Flask) -> None:
    """Close the predictions.sqlite connection at the end of each request.

    Args:
        app: Flask application
    """
    app.teardown_appcontext(close_predictions_db)
