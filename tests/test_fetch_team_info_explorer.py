"""Tests for _fetch_team_from_explorer_api function."""

from unittest.mock import patch

from backend.stats import ApiError, TeamStats, _fetch_team_from_explorer_api


class TestFetchTeamFromExplorerApi:
    """Test suite for _fetch_team_from_explorer_api function."""

    @patch("backend.stats._fetch_team_info")
    @patch("backend.stats._safe_get_json")
    def test_fetch_by_team_name_success(self, mock_get_json, mock_fetch_info):
        """Test successful team info fetch by team name."""
        # Mock successful API response
        mock_response = {
            "command": "SELECT",
            "rows": [{"team_id": 39, "name": "Team Spirit", "tag": "TS", "rating": 2500.5, "delta": 25.3}],
        }
        mock_get_json.return_value = (mock_response, None)
        mock_fetch_info.return_value = ({"logo_url": "http://example.com/logo.png"}, None)

        result = _fetch_team_from_explorer_api(team_str="Spirit")

        assert isinstance(result, TeamStats)
        assert result.error is None
        assert result.team_id == 39
        assert result.team == "Team Spirit"
        assert result.tag == "TS"
        assert result.rating == 2500.5
        assert result.delta == 25.3
        assert result.logo_url == "http://example.com/logo.png"
        assert result.players == []
        assert result.other_players == []

    @patch("backend.stats._fetch_team_info")
    @patch("backend.stats._safe_get_json")
    def test_fetch_by_team_id_success(self, mock_get_json, mock_fetch_info):
        """Test successful team info fetch by team ID."""
        # Mock successful API response
        mock_response = {
            "command": "SELECT",
            "rows": [{"team_id": 123, "name": "Test Team", "tag": "TT", "rating": 2000.0, "delta": 10.0}],
        }
        mock_get_json.return_value = (mock_response, None)
        mock_fetch_info.return_value = ({"logo_url": "http://example.com/test.png"}, None)

        result = _fetch_team_from_explorer_api(team_id=123)

        assert isinstance(result, TeamStats)
        assert result.error is None
        assert result.team_id == 123
        assert result.team == "Test Team"
        assert result.tag == "TT"
        assert result.players == []
        assert result.other_players == []

    @patch("backend.stats._fetch_team_info")
    @patch("backend.stats._safe_get_json")
    def test_fetch_handles_missing_rating_and_delta(self, mock_get_json, mock_fetch_info):
        """Test that missing rating and delta are handled gracefully."""
        mock_response = {
            "command": "SELECT",
            "rows": [{"team_id": 100, "name": "Team", "tag": "T", "rating": None, "delta": None}],
        }
        mock_get_json.return_value = (mock_response, None)
        mock_fetch_info.return_value = ({}, None)

        result = _fetch_team_from_explorer_api(team_str="Team")

        assert isinstance(result, TeamStats)
        assert result.team_id == 100
        assert result.rating is None
        assert result.delta is None
        assert result.error is None
        assert result.logo_url is None
        assert result.players == []
        assert result.other_players == []

    @patch("backend.stats._safe_get_json")
    def test_fetch_handles_network_error(self, mock_get_json):
        """Test error handling when API request fails."""
        api_error = ApiError(status=503, code="NETWORK_ERROR", message="Connection timeout")
        mock_get_json.return_value = (None, api_error)

        result = _fetch_team_from_explorer_api(team_str="NonExistent")

        assert isinstance(result, TeamStats)
        assert result.error is not None
        assert result.error.status == 503
        assert result.error.code == "NETWORK_ERROR"
        assert result.team_id is None

    @patch("backend.stats._safe_get_json")
    def test_fetch_handles_malformed_response(self, mock_get_json):
        """Test error handling for malformed API response."""
        mock_response = {
            "command": "SELECT",
            "rows": [],  # Empty rows - no teams found
        }
        mock_get_json.return_value = (mock_response, None)

        result = _fetch_team_from_explorer_api(team_str="NonExistent")

        assert isinstance(result, TeamStats)
        assert result.error is not None
        assert result.error.code == "RESPONSE_PARSE_ERROR"
        assert result.team_id is None

    @patch("backend.stats._safe_get_json")
    def test_fetch_handles_invalid_command(self, mock_get_json):
        """Test error handling when response has invalid command."""
        mock_response = {
            "command": "DELETE",  # Invalid command
            "rows": [{"team_id": 39}],
        }
        mock_get_json.return_value = (mock_response, None)

        result = _fetch_team_from_explorer_api(team_str="Team")

        assert isinstance(result, TeamStats)
        assert result.error is not None
        assert result.error.status == 502

    def test_fetch_mutually_exclusive_params(self):
        """Test that team_str and team_id cannot be provided together."""
        result = _fetch_team_from_explorer_api(team_str="Alpha", team_id=123)
        assert isinstance(result, TeamStats)
        assert result.error is not None
        assert result.error.code == "INVALID_PARAMETER"

    def test_fetch_missing_both_params(self):
        """Test that at least one parameter must be provided."""
        result = _fetch_team_from_explorer_api()
        assert isinstance(result, TeamStats)
        assert result.error is not None
        assert result.error.code == "INVALID_PARAMETER"

    @patch("backend.stats._safe_get_json")
    def test_fetch_includes_url_in_error_details(self, mock_get_json):
        """Test that error details include the API URL."""
        api_error = ApiError(status=503, code="NETWORK_ERROR", message="Failed")
        mock_get_json.return_value = (None, api_error)

        result = _fetch_team_from_explorer_api(team_str="Team")

        assert result.error is not None
        assert result.error.details is not None
        assert "url" in result.error.details
        assert "explorer" in result.error.details["url"]
        assert "opendota.com/api/explorer" in result.error.details["url"]

    @patch("backend.stats._fetch_team_info")
    @patch("backend.stats._safe_get_json")
    def test_fetch_handles_missing_fields_in_response(self, mock_get_json, mock_fetch_info):
        """Test error handling when required fields are missing."""
        mock_response = {
            "command": "SELECT",
            "rows": [{"team_id": 39, "name": "Team Spirit"}],  # Missing tag
        }
        mock_get_json.return_value = (mock_response, None)
        mock_fetch_info.return_value = ({}, None)

        result = _fetch_team_from_explorer_api(team_str="Spirit")

        assert isinstance(result, TeamStats)
        assert result.error is not None
        assert result.error.code == "RESPONSE_PARSE_ERROR"

    @patch("backend.stats._fetch_team_info")
    @patch("backend.stats._safe_get_json")
    def test_fetch_by_team_name_builds_correct_sql(self, mock_get_json, mock_fetch_info):
        """Test that team name fetches build correct SQL query."""
        mock_response = {
            "command": "SELECT",
            "rows": [{"team_id": 1, "name": "Test", "tag": "T", "rating": 100.0, "delta": 10.0}],
        }
        mock_get_json.return_value = (mock_response, None)
        mock_fetch_info.return_value = ({}, None)

        _fetch_team_from_explorer_api(team_str="TestTeam")

        # Verify that _safe_get_json was called
        assert mock_get_json.called
        call_args = mock_get_json.call_args
        called_url = call_args[0][0]
        # URL should contain explorer API endpoint
        assert "explorer" in called_url
        assert "sql=" in called_url

    @patch("backend.stats._fetch_team_info")
    @patch("backend.stats._safe_get_json")
    def test_fetch_by_team_id_builds_correct_sql(self, mock_get_json, mock_fetch_info):
        """Test that team ID fetches build correct SQL query."""
        mock_response = {
            "command": "SELECT",
            "rows": [{"team_id": 123, "name": "Test", "tag": "T", "rating": 100.0, "delta": 10.0}],
        }
        mock_get_json.return_value = (mock_response, None)
        mock_fetch_info.return_value = ({}, None)

        _fetch_team_from_explorer_api(team_id=123)

        # Verify that _safe_get_json was called
        assert mock_get_json.called
        # Get the URL that was called
        call_args = mock_get_json.call_args
        called_url = call_args[0][0]
        # URL should contain explorer endpoint for ID-based lookup
        assert "explorer" in called_url

    @patch("backend.stats._fetch_team_info")
    @patch("backend.stats._safe_get_json")
    def test_fetch_handles_non_numeric_rating(self, mock_get_json, mock_fetch_info):
        """Test handling of non-numeric rating value."""
        mock_response = {
            "command": "SELECT",
            "rows": [{"team_id": 39, "name": "Team", "tag": "T", "rating": "invalid", "delta": 10.0}],
        }
        mock_get_json.return_value = (mock_response, None)
        mock_fetch_info.return_value = ({}, None)

        result = _fetch_team_from_explorer_api(team_str="Team")

        assert isinstance(result, TeamStats)
        # Should handle the invalid rating gracefully
        assert result.team_id == 39
        assert result.rating is None
