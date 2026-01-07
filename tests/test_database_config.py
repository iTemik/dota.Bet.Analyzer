import os
from backend import create_app


def test_default_database_filename():
    app = create_app(test_config={})
    db_path = app.config['DATABASE']
    assert db_path.endswith(os.path.join(app.instance_path, 'dba.sqlite'))


def test_custom_database_filename():
    app = create_app(test_config={'DATABASE_FILENAME': 'custom.db'})
    db_path = app.config['DATABASE']
    assert db_path.endswith(os.path.join(app.instance_path, 'custom.db'))
