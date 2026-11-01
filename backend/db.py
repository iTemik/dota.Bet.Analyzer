"""SQLite connections for both app databases, one per request (closed at app context teardown).

- d2ba.sqlite: OpenDota/Liquipedia cache, safe to delete (`get_cache_db`)
- predictions.sqlite: the user's snapshots and predictions, back it up (`get_user_db`)

Both files live in the Flask instance folder. Their tables come from the migrations that `npm run migrate`
(scripts/init_d2ba_db.py) applies; scripts/migrate.py names each file `<DATABASES key>.sqlite`, matching the names
below.
"""

import os
import sqlite3
from typing import cast

from flask import Flask, current_app, g

CACHE_DB_FILENAME = "d2ba.sqlite"
USER_DB_FILENAME = "predictions.sqlite"


def get_cache_db() -> sqlite3.Connection:
    """Get the request's connection to the d2ba.sqlite cache.

    Returns:
        Connection with rows as sqlite3.Row
    """
    if "cache_db" not in g:
        db_path = os.path.join(current_app.instance_path, CACHE_DB_FILENAME)
        g.cache_db = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        g.cache_db.row_factory = sqlite3.Row
    return cast(sqlite3.Connection, g.cache_db)


def get_user_db() -> sqlite3.Connection:
    """Get the request's connection to predictions.sqlite (user data), with foreign keys on.

    Returns:
        Connection with rows as sqlite3.Row
    """
    if "user_db" not in g:
        db_path = os.path.join(current_app.instance_path, USER_DB_FILENAME)
        g.user_db = sqlite3.connect(db_path)
        g.user_db.row_factory = sqlite3.Row
        g.user_db.execute("PRAGMA foreign_keys = ON")
    return cast(sqlite3.Connection, g.user_db)


def close_dbs(e: BaseException | None = None) -> None:
    """Close the connections this app context opened, if any."""
    for key in ("cache_db", "user_db"):
        db = g.pop(key, None)
        if db is not None:
            db.close()


def init_app(app: Flask) -> None:
    """Close the database connections at the end of each request.

    Args:
        app: Flask application
    """
    app.teardown_appcontext(close_dbs)
