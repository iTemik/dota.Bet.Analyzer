import inspect

from flask import Flask

import backend.db as db_mod


def test_init_app_annotation():
    sig = inspect.signature(db_mod.init_app)
    params = sig.parameters
    assert "app" in params
    ann = params["app"].annotation
    assert ann is Flask or getattr(ann, "__name__", None) == "Flask"
