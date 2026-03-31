#!/usr/bin/env python3
"""
Database migration runner following best practices.

Features:
- Tracks applied migrations in migration_history table
- Executes migrations in order based on filename (YYYYMMDD_HHMMSS style)
- Supports idempotent migrations (duplicate column/object errors are silently skipped)
"""

import sqlite3
import sys
from pathlib import Path
from typing import List

_STATEMENT_PREVIEW_LEN = 80  # characters of a statement shown in log messages


class MigrationRunner:
    """Runs database migrations with tracking support."""

    def __init__(self, db_path: str | None = None):
        """Initialize migration runner.

        Args:
            db_path: Path to database file. If None, uses instance/d2ba.sqlite
        """
        if db_path is None:
            script_dir = Path(__file__).parent
            project_root = script_dir.parent
            instance_dir = project_root / "instance"
            instance_dir.mkdir(exist_ok=True)
            self.db_path = str(instance_dir / "d2ba.sqlite")
        else:
            self.db_path = db_path

        script_dir = Path(__file__).parent
        project_root = script_dir.parent
        self.migrations_dir = project_root / "backend" / "migrations"

        if not self.migrations_dir.exists():
            raise FileNotFoundError(f"Migrations directory not found: {self.migrations_dir}")

    def get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def create_migrations_table(self, conn: sqlite3.Connection) -> None:
        """Create migration_history table if it doesn't exist.

        Args:
            conn: Database connection
        """
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS migration_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                migration_name TEXT UNIQUE NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'applied'
            )
            """
        )
        conn.commit()

    def get_applied_migrations(self, conn: sqlite3.Connection) -> set[str]:
        """Get set of already applied migration names.

        Args:
            conn: Database connection

        Returns:
            Set of applied migration filenames
        """
        cursor = conn.cursor()
        cursor.execute("SELECT migration_name FROM migration_history WHERE status = 'applied'")
        return {row[0] for row in cursor.fetchall()}

    def get_pending_migrations(self) -> List[Path]:
        """Get list of pending migrations in order.

        Returns:
            List of migration file paths sorted by filename
        """
        conn = self.get_connection()
        self.create_migrations_table(conn)
        applied = self.get_applied_migrations(conn)
        conn.close()

        # Get all SQL migration files sorted by filename (YYYYMMDD_HHMMSS convention)
        migration_files = sorted(self.migrations_dir.glob("*.sql"))

        # Filter to pending migrations
        pending = [f for f in migration_files if f.name not in applied]

        return pending

    def run_migration(self, migration_path: Path) -> bool:
        """Run a single migration.

        Executes each SQL statement in the migration file individually so that
        idempotency checks are applied per-statement and all statements are
        attempted before the migration is recorded as applied.  If any
        non-idempotent statement raises an error the migration is aborted and
        NOT recorded.

        Args:
            migration_path: Path to migration SQL file

        Returns:
            True if all statements succeeded, False otherwise
        """
        try:
            conn = self.get_connection()
            self.create_migrations_table(conn)

            # Read migration file
            with open(migration_path, "r", encoding="utf-8") as f:
                sql = f.read()

            cursor = conn.cursor()

            # Split into individual statements and execute each one separately.
            # This ensures that a "duplicate column / already exists" error in
            # one statement does not silently prevent the remaining statements
            # from running, and that the migration is only recorded once every
            # statement has been processed successfully.
            #
            # Assumption: migration files contain only DDL statements (CREATE,
            # ALTER, CREATE INDEX, PRAGMA) and do not embed semicolons inside
            # string literals or comments, so a simple split on ";" is safe.
            statements = [s.strip() for s in sql.split(";") if s.strip()]
            for statement in statements:
                try:
                    cursor.execute(statement)
                except sqlite3.OperationalError as e:
                    error_msg = str(e).lower()
                    if "already exists" in error_msg or "duplicate column" in error_msg:
                        preview = statement[:_STATEMENT_PREVIEW_LEN].splitlines()[0]
                        print(f"  ⓘ  Skipping (idempotent): {preview}")
                    else:
                        raise

            # Record migration as applied only after all statements succeed
            cursor.execute(
                "INSERT OR IGNORE INTO migration_history (migration_name, status) VALUES (?, 'applied')",
                (migration_path.name,),
            )
            conn.commit()
            conn.close()

            return True

        except Exception as e:
            print(f"✗ Failed to apply {migration_path.name}: {e}")
            if "conn" in locals():
                conn.close()
            return False

    def run_all_pending(self) -> bool:
        """Run all pending migrations.

        Returns:
            True if all succeeded, False if any failed
        """
        pending = self.get_pending_migrations()

        if not pending:
            print("✓ Database is up to date. No pending migrations.")
            return True

        print(f"Found {len(pending)} pending migration(s):")
        for migration_path in pending:
            print(f"  → {migration_path.name}")

        print("\nApplying migrations...")
        all_succeeded = True

        for migration_path in pending:
            success = self.run_migration(migration_path)
            if success:
                print(f"✓ Applied {migration_path.name}")
            else:
                all_succeeded = False

        if all_succeeded:
            print(f"\n✓ Successfully applied {len(pending)} migration(s)")
        else:
            print("\n✗ Some migrations failed")

        return all_succeeded

    def show_status(self) -> None:
        """Show migration status."""
        conn = self.get_connection()
        self.create_migrations_table(conn)

        cursor = conn.cursor()
        cursor.execute("SELECT migration_name, applied_at FROM migration_history ORDER BY migration_name")
        applied = cursor.fetchall()

        all_migrations = sorted(self.migrations_dir.glob("*.sql"))
        applied_names = {m[0] for m in applied}

        print("Migration Status:")
        print("-" * 60)

        for migration in sorted(all_migrations, key=lambda x: x.name):
            if migration.name in applied_names:
                timestamp = next(a[1] for a in applied if a[0] == migration.name)
                print(f"✓ {migration.name:<45} (applied at {timestamp})")
            else:
                print(f"○ {migration.name:<45} (pending)")

        conn.close()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Database migration runner")
    parser.add_argument(
        "command",
        choices=["run", "status"],
        help="Command to execute",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Path to database file (default: instance/d2ba.sqlite)",
    )

    args = parser.parse_args()

    try:
        runner = MigrationRunner(db_path=args.db)

        if args.command == "run":
            success = runner.run_all_pending()
            sys.exit(0 if success else 1)
        elif args.command == "status":
            runner.show_status()
            sys.exit(0)

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
