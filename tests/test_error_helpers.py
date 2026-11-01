"""Tests for the error helpers in backend.helpers."""

from backend.helpers import ApiError, Errors, api_error


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
