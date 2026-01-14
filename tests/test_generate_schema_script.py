from pathlib import Path

import scripts.generate_schema as gs  # type: ignore[import-untyped]


def test_generate_matches_existing_file():
    txt = Path("backend/schema.txt").read_text()
    generated = gs.generate_sql_from_json_text(txt)
    existing = Path("backend/opendota_schema.sql").read_text()
    # Normalize trailing whitespace/newline differences
    assert generated.rstrip() == existing.rstrip()


def test_cli_check_exit_zero_on_match(tmp_path, monkeypatch):
    # Write a temp copy of schema.txt and opendota_schema.sql then run --check
    schema_txt = tmp_path / "schema.txt"
    schema_sql = tmp_path / "opendota_schema.sql"
    content = Path("backend/schema.txt").read_text()
    schema_txt.write_text(content)
    schema_sql.write_text(gs.generate_sql_from_json_text(content))

    # Run main with --check against temp files
    rc = gs.main(["--input", str(schema_txt), "--output", str(schema_sql), "--check"])
    assert rc == 0
