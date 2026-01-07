import os
import threading

from flask import Flask

__version__ = "0.1"

# Module-level singleton and a lock to make creation thread-safe
_app = None
_app_lock = threading.Lock()


def create_app(test_config=None):
    global _app

    # If not in test mode and an instance already exists, return it (singleton)
    if test_config is None and _app is not None:
        return _app

    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev',
        DATABASE_FILENAME='dba.sqlite',
    )

    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    # Ensure DATABASE is constructed from configurable filename (DATABASE_FILENAME)
    db_filename = app.config.get('DATABASE_FILENAME', 'dba.sqlite')
    app.config['DATABASE'] = os.path.join(app.instance_path, db_filename)

    # a simple page that says hello
    @app.route('/hello')
    def hello():
        return 'Hello, World!'

    from . import db
    # Call init_app if the db module provides it (optional)
    if hasattr(db, 'init_app'):
        db.init_app(app)

    if test_config is None:
        with _app_lock:
            if _app is None:
                _app = app
            # Always return the module-level singleton in non-test mode
            return _app
        
    
       
    return app