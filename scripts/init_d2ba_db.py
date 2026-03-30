#!/usr/bin/env python3
"""Initialize d2ba.sqlite database for Dota 2 Bet Analyzer.

This script initializes the database and runs all pending migrations.
Uses the migration runner in scripts/migrate.py for best practices.
"""

import argparse
import sys
from pathlib import Path


def init_d2ba_db(db_path=None):
    """Initialize the d2ba.sqlite database and run migrations.

    Args:
        db_path: Path to the database file. If None, uses instance/d2ba.sqlite

    Returns:
        True if successful, False otherwise
    """
    try:
        # Import the migration runner at runtime
        script_dir = Path(__file__).parent
        sys.path.insert(0, str(script_dir))
        from migrate import MigrationRunner

        runner = MigrationRunner(db_path=db_path)

        print("Initializing d2ba database...")
        success = runner.run_all_pending()

        if success:
            print(f"\nDatabase initialized successfully at: {runner.db_path}")
        else:
            print("\nDatabase initialization failed. Some migrations could not be applied.")

        return success

    except Exception as e:
        print(f"Error initializing database: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize d2ba database")
    parser.add_argument(
        "--db",
        default=None,
        help="Path to database file (default: instance/d2ba.sqlite)",
    )

    args = parser.parse_args()
    try:
        success = init_d2ba_db(db_path=args.db)
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
