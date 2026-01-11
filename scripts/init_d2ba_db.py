#!/usr/bin/env python3
"""Initialize d2ba.sqlite database for Dota 2 Bet Analyzer."""

import os
import sqlite3
import sys


def init_d2ba_db(db_path=None):
    """Initialize the d2ba.sqlite database.

    Args:
        db_path: Path to the database file. If None, uses instance/d2ba.sqlite
    """
    if db_path is None:
        # Get the project root directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        instance_dir = os.path.join(project_root, "instance")
        os.makedirs(instance_dir, exist_ok=True)
        db_path = os.path.join(instance_dir, "d2ba.sqlite")

    # Get the schema file path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(os.path.dirname(script_dir), "backend")
    schema_path = os.path.join(backend_dir, "d2ba_schema.sql")

    if not os.path.exists(schema_path):
        print(f"Error: Schema file not found at {schema_path}")
        return False

    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Read and execute schema
        with open(schema_path, encoding="utf8") as f:
            schema = f.read()
            cursor.executescript(schema)

        conn.commit()
        conn.close()

        print(f"Successfully initialized d2ba database at: {db_path}")
        return True

    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else None
    success = init_d2ba_db(db_path)
    sys.exit(0 if success else 1)
