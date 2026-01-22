import pytest

from backend import create_app


@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


class TestTeamsSearch:
    """Test the /api/teams/search endpoint"""

    def test_search_teams_missing_query(self, client):
        """Test search without query parameter"""
        response = client.get("/api/teams/search")
        assert response.status_code == 400
        data = response.get_json()
        assert "message" in data
        assert "at least 2 characters" in data["message"].lower()

    def test_search_teams_too_short_query(self, client):
        """Test search with query less than 2 characters"""
        response = client.get("/api/teams/search?q=L")
        assert response.status_code == 400
        data = response.get_json()
        assert "at least 2 characters" in data["message"].lower()

    def test_search_teams_empty_query(self, client):
        """Test search with empty query"""
        response = client.get("/api/teams/search?q=")
        assert response.status_code == 400

    def test_search_teams_whitespace_only(self, client):
        """Test search with whitespace-only query"""
        response = client.get("/api/teams/search?q=%20%20")
        assert response.status_code == 400
