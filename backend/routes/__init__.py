"""REST routes under /api, one flask-smorest blueprint per module (one Swagger section each).

`ApiBlueprint` adds `error_response` (the Swagger doc of an `api_error` response); `register_routes` registers
every blueprint on the app's Api.
"""

from collections.abc import Callable
from typing import Any

from flask_smorest import Api, Blueprint

from backend.helpers import ErrorDefinition
from backend.schemas import ErrorSchema

API_PREFIX = "/api"


class ApiBlueprint(Blueprint):
    """flask-smorest Blueprint with the /api prefix and the `error_response` Swagger helper."""

    def __init__(self, name: str, import_name: str, description: str) -> None:
        """Create a blueprint served under /api.

        Args:
            name: Blueprint name (also the Swagger section title)
            import_name: The route module's `__name__`
            description: Swagger section description
        """
        super().__init__(name, import_name, url_prefix=API_PREFIX, description=description)

    def error_response(self, status: int, error: ErrorDefinition, description: str, **details: Any) -> Callable:
        """Swagger doc for an `api_error` response: ErrorSchema with an example built from the Errors entry.

        Args:
            status: HTTP status code
            error: ErrorDefinition from Errors (gives the example's code and message)
            description: What causes this response
            **details: Example `details` besides `url`, which every error carries

        Returns:
            The flask-smorest `alt_response` decorator
        """
        example = {
            "status": status,
            "code": error.code,
            "message": error.message,
            "details": {"url": "/api/...", **details},
        }
        decorator: Callable = self.alt_response(status, schema=ErrorSchema, description=description, example=example)
        return decorator


def register_routes(api: Api) -> None:
    """Register every route blueprint on the app's Api.

    Args:
        api: The flask-smorest Api of the app
    """
    from backend.routes import catalog, jobs, predictions, statistics

    for module in (statistics, predictions, catalog, jobs):
        api.register_blueprint(module.bp)
