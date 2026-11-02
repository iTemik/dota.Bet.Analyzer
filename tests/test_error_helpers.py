"""Tests for the error helpers in backend.helpers."""

from backend.helpers import ApiError, ErrorDefinition, Errors, api_error


def test_api_error_of_uses_definition():
    error = ApiError.of(Errors.INVALID_TEAM_ID, 400, team_id=-1)
    assert (error.status, error.code, error.message) == (400, "INVALID_TEAM_ID", Errors.INVALID_TEAM_ID.message)
    assert error.details == {"team_id": -1}


def test_api_error_adds_url_and_exception(app):
    with app.test_request_context("/api/heroes/meta"):
        response, status = api_error(503, Errors.FAILED_TO_FETCH_HERO_STATS, ValueError("down"), page=2)
    assert status == 503
    assert response.get_json() == {
        "status": 503,
        "code": "FAILED_TO_FETCH_HERO_STATS",
        "message": Errors.FAILED_TO_FETCH_HERO_STATS.message,
        "details": {"url": "/api/heroes/meta", "exception": "down", "page": 2},
    }


def _error_responses(client) -> list[tuple[str, str, str, dict]]:
    """(path, method, status, response) for every ErrorSchema response in the OpenAPI spec."""
    spec = client.get("/api/openapi.json").get_json()
    found = []
    for path, methods in spec["paths"].items():
        for method, operation in methods.items():
            if not isinstance(operation, dict):
                continue
            for status, response in operation.get("responses", {}).items():
                content = response.get("content", {}).get("application/json", {})
                if content.get("schema", {}).get("$ref", "").endswith("/ApiError"):
                    found.append((path, method, status, content))
    return found


def test_every_documented_error_has_an_example_from_errors(client):
    known = {
        definition.code: definition.message
        for definition in vars(Errors).values()
        if isinstance(definition, ErrorDefinition)
    }
    responses = _error_responses(client)
    assert len(responses) >= 40
    for path, method, status, content in responses:
        example = content.get("example")
        assert example, f"{method.upper()} {path} {status} has no example"
        assert example["status"] == int(status), (path, method, status)
        assert known.get(example["code"]) == example["message"], (path, method, status)
        assert example["details"]["url"] == "/api/..."


def test_error_response_example_carries_details(client):
    by_key = {(path, method, status): content for path, method, status, content in _error_responses(client)}
    example = by_key[("/api/jobs/{name}/run", "post", "404")]["example"]
    assert example == {
        "status": 404,
        "code": "JOB_NOT_FOUND",
        "message": Errors.JOB_NOT_FOUND.message,
        "details": {"url": "/api/...", "name": "x"},
    }
