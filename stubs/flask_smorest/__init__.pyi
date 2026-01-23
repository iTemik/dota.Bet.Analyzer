"""Type stubs for flask_smorest."""

from typing import Any

from flask import Flask

class Api:
    """Flask-smorest API class."""

    def __init__(self, app: Flask | None = None, *, spec_kwargs: dict[str, Any] | None = None) -> None: ...
    def register_blueprint(self, blp: Any, **options: Any) -> None: ...

class Blueprint:
    """Flask-smorest Blueprint class."""

    def __init__(
        self,
        name: str,
        import_name: str,
        *,
        url_prefix: str | None = None,
        description: str | None = None,
        **kwargs: Any,
    ) -> None: ...
    def route(self, rule: str, **options: Any) -> Any: ...
    def arguments(self, schema: Any, **kwargs: Any) -> Any: ...
    def response(self, code: int, schema: Any | None = None, **kwargs: Any) -> Any: ...
    def alt_response(self, code: int, schema: Any | None = None, **kwargs: Any) -> Any: ...

def abort(code: int, message: str | None = None, **kwargs: Any) -> Any: ...
