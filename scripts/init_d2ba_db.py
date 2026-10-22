#!/usr/bin/env python3
"""Initialize the Dota 2 Bet Analyzer databases: d2ba.sqlite (OpenDota cache) and predictions.sqlite.

This script initializes the databases and runs all pending migrations.
Uses the migration runner in scripts/migrate.py for best practices.
"""

import argparse
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def init_d2ba_db(db_path=None):
    """Initialize the d2ba.sqlite database and run migrations.

    Args:
        db_path: Path to the database file. If None, uses instance/d2ba.sqlite

    Returns:
        True if successful, False otherwise
    """
    return init_db("d2ba", db_path)


def init_predictions_db(db_path=None):
    """Initialize the predictions.sqlite database (snapshots and predictions) and run migrations.

    Args:
        db_path: Path to the database file. If None, uses instance/predictions.sqlite

    Returns:
        True if successful, False otherwise
    """
    return init_db("predictions", db_path)


def init_db(database, db_path=None):
    """Initialize one database and run its migrations.

    Args:
        database: Database name from scripts/migrate.py DATABASES
        db_path: Path to the database file. If None, uses instance/<database>.sqlite

    Returns:
        True if successful, False otherwise
    """
    try:
        # Import the migration runner at runtime
        script_dir = Path(__file__).parent
        script_dir_str = str(script_dir)
        if script_dir_str not in sys.path:
            sys.path.insert(0, script_dir_str)
        from migrate import MigrationRunner

        runner = MigrationRunner(db_path=db_path, database=database)

        logger.info(f"Initializing {database} database...")
        success = runner.run_all_pending()

        if success:
            logger.info(f"Database initialized successfully at: {runner.db_path}")
        else:
            logger.error("Database initialization failed. Some migrations could not be applied.")

        return success

    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Initialize d2ba and predictions databases")
    parser.add_argument(
        "--db",
        default=None,
        help="Path to d2ba database file (default: instance/d2ba.sqlite)",
    )
    parser.add_argument(
        "--predictions-db",
        default=None,
        help="Path to predictions database file (default: instance/predictions.sqlite)",
    )

    args = parser.parse_args()
    try:
        success = init_d2ba_db(db_path=args.db)
        success = init_predictions_db(db_path=args.predictions_db) and success
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)
