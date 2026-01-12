"""Regenerate SQLite schema (backend/opendota_schema.sql) from backend/schema.txt.

Usage:
    python scripts/generate_schema.py [--input backend/schema.txt] [--output backend/opendota_schema.sql] [--check]

If --check is provided the script will compare generated SQL to the existing output file and
return non-zero exit code on mismatch (useful in CI).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, Mapping


def singularize(name: str) -> str:
    if name.endswith("ies"):
        return name[:-3] + "y"
    if name.endswith("s"):
        return name[:-1]
    return name


def map_type(col_name: str, data_type: str) -> str:
    s = data_type.lower()
    # Timestamp-like -> INTEGER (Unix epoch)
    if "timestamp" in s or "date" in s or " time" in s or col_name.endswith("_time") or col_name.endswith("time"):
        return "INTEGER"
    if "bigint" in s or s == "integer" or "integer" in s or "smallint" in s:
        return "INTEGER"
    if "double" in s or "real" in s or "numeric" in s:
        return "REAL"
    if "boolean" in s:
        return "BOOLEAN"
    if "json" in s or "array" in s:
        return "JSON"
    if "text" in s:
        return "TEXT"
    if "uuid" in s:
        return "TEXT"
    # fallback
    return "TEXT"


def infer_primary_keys(tables: Mapping[str, Iterable[Dict[str, str]]]) -> set:
    pk_candidates = set()
    for table, cols in tables.items():
        sing = singularize(table)
        for col in cols:
            cname = col["name"]
            if cname == "id" or cname == f"{table}_id" or cname == f"{sing}_id":
                pk_candidates.add((table, cname))
            # some known explicit candidates
            if table == "webhooks" and cname == "hook_id":
                pk_candidates.add((table, cname))
    return pk_candidates


def generate_sql_from_json_text(json_text: str) -> str:
    cols = json.loads(json_text)
    tables: Dict[str, list] = {}
    for c in cols:
        t = c["table_name"]
        tables.setdefault(t, []).append({"name": c["column_name"], "type": c["data_type"]})

    index_columns = {
        "account_id",
        "match_id",
        "match_seq_num",
        "leagueid",
        "team_id",
        "player_slot",
        "api_key",
        "hook_id",
    }

    sql_lines = []
    sql_lines.append(
        "-- Auto-generated SQLite schema from backend/schema.txt which is the response of opendota api: https://api.opendota.com/api/schema"
    )
    sql_lines.append("-- Generated: primary keys inferred where safe, timestamps stored as INTEGER (Unix epoch)")
    sql_lines.append("PRAGMA foreign_keys = ON;")
    sql_lines.append("")

    pk_candidates = infer_primary_keys(tables)

    indices = []
    for table, cols in sorted(tables.items()):
        sql_lines.append(f'CREATE TABLE IF NOT EXISTS "{table}" (')
        col_defs = []
        for col in cols:
            cname = col["name"]
            ctype = map_type(cname, col["type"])
            pk = ""
            if (table, cname) in pk_candidates:
                pk = " PRIMARY KEY"
            col_defs.append(f'  "{cname}" {ctype}{pk}')
            if cname in index_columns:
                indices.append((table, cname))
        sql_lines.append(",\n".join(col_defs))
        sql_lines.append(");")
        sql_lines.append("")

    seen_idx = set()
    for table, col in indices:
        name = f"idx_{table}_{col}"
        if name in seen_idx:
            continue
        seen_idx.add(name)
        sql_lines.append(f'CREATE INDEX IF NOT EXISTS "{name}" ON "{table}" ("{col}");')

    return "\n".join(sql_lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", "-i", default="backend/schema.txt")
    parser.add_argument("--output", "-o", default="backend/opendota_schema.sql")
    parser.add_argument(
        "--check", action="store_true", help="Compare generated output to existing file and exit non-zero on mismatch"
    )
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 2

    json_text = input_path.read_text()
    generated = generate_sql_from_json_text(json_text)

    if args.check:
        if not output_path.exists():
            print(f"Output file {output_path} does not exist to compare against.", file=sys.stderr)
            return 2
        existing = output_path.read_text()
        if existing != generated:
            print("Generated schema differs from existing file.", file=sys.stderr)
            return 3
        print("Generated schema matches existing file.")
        return 0

    output_path.write_text(generated)
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
