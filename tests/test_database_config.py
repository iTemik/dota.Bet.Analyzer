import os
import sys
from pathlib import Path

# Add the parent directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "dota.Bet.Analyzer"))

from backend import create_app  # type: ignore[import-untyped]


def test_default_database_filename():
    app = create_app(test_config={})
    db_path = app.config["DATABASE"]
    assert db_path.endswith(os.path.join(app.instance_path, "d2ba.sqlite"))


def test_custom_database_filename():
    app = create_app(test_config={"DATABASE_FILENAME": "custom.db"})
    db_path = app.config["DATABASE"]
    assert db_path.endswith(os.path.join(app.instance_path, "custom.db"))
