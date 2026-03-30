# Database Migrations

This directory contains SQL migrations for the d2ba database, following best practices.

## Structure

- Each migration is a `.sql` file named with timestamp: `YYYYMMDD_HHMMSS_description.sql`
- Migrations are applied in alphabetical order (which preserves chronological order)
- A `migration_history` table tracks which migrations have been applied

## Running Migrations

### Automatic (Recommended)
Initialize the database with migrations:
```bash
python scripts/init_d2ba_db.py
```

### Manual
Run the migration runner directly:
```bash
python scripts/migrate.py run              # Apply pending migrations
python scripts/migrate.py status           # Show migration status
python scripts/migrate.py run --db <path>  # Use custom database path
```

## Writing New Migrations

1. **Create a new file** with naming convention: `YYYYMMDD_HHMMSS_description.sql`
2. **Make migrations idempotent** - safe to run multiple times:
   - Use `IF NOT EXISTS` for CREATE statements
   - Use `IF EXISTS` for DROP statements
   - Handle "already exists" errors gracefully

3. **Add documentation header**:
```sql
-- Migration: 20260327_000003_my_migration.sql
-- Description: Clear description of what this migration does
-- Created: 2026-03-27
-- Dependencies: previous_migration (if applicable)
```

## Example Idempotent Migration

```sql
-- Migration: 20260327_000003_add_new_column.sql
-- Description: Add new_column to teams table
-- Created: 2026-03-27

-- Add column safely - SQLite will handle duplicates
ALTER TABLE teams ADD COLUMN new_column TEXT DEFAULT NULL;

-- Note: SQLite raises "duplicate column name" error if column exists.
-- The migration runner handles this gracefully for idempotency.
```
