"""Tests for compute_statistics function with both team names and team IDs."""

from unittest.mock import MagicMock, patch

import pytest

from backend.stats import ApiError, Player, StatsResponse, TeamStats, compute_statistics


class TestComputeStatisticsByNames:
    """Test suite for compute_statistics with team names."""

    @patch("backend.stats._fetch_team_from_explorer_api")
    @patch("backend.stats.get_players_by_team")
    def test_compute_by_names_success(self, mock_get_players, mock_fetch_info, monkeypatch):
        """Test successful computation with team names."""
        # Mock fetch_info to return TeamStats
        mock_fetch_info.return_value = TeamStats(
            team_id=39,
            team="Team Spirit",
            tag="TS",
            rating=2500.0,
            delta=25.0,
            logo_url="http://example.com/logo.png",
        )
        # Mock get_players
        mock_get_players.return_value = (
            [Player(name="Player1", id=1), Player(name="Player2", id=2)],
            [],
        )
        # Mock Celery task
        mock_task = MagicMock()
        monkeypatch.setattr("backend.dota_bet_analyzer.players_statistics_task", mock_task)

        result = compute_statistics(teams=["Spirit"])

        assert isinstance(result, StatsResponse)
        assert len(result.teams) == 1
        team = result.teams[0]
        assert team.team_id == 39
        assert team.team == "Team Spirit"
        assert team.tag == "TS"
        assert team.rating == 2500.0
        assert len(team.players) == 2

    @patch("backend.stats._fetch_team_from_explorer_api")
    @patch("backend.stats.get_players_by_team")
    def test_compute_by_names_no_players(self, mock_get_players, mock_fetch_info):
        """Test computation when team has no players."""
        mock_fetch_info.return_value = TeamStats(
            team_id=100,
            team="Empty Team",
            tag="ET",
            rating=1000.0,
            delta=0.0,
        )
        mock_get_players.return_value = ([], [])  # No players

        result = compute_statistics(teams=["Empty"])

        assert len(result.teams) == 1
        team = result.teams[0]
        assert len(team.players) == 0
        assert team.task_id is None  # No task created without players

    @patch("backend.stats._fetch_team_from_explorer_api")
    def test_compute_by_names_fetch_error(self, mock_fetch_info):
        """Test error handling when team fetch fails."""
        error = ApiError(status=503, code="NETWORK_ERROR", message="Connection failed")
        mock_fetch_info.return_value = TeamStats(error=error, team="NonExistent")

        result = compute_statistics(teams=["NonExistent"])

        assert len(result.teams) == 1
        team = result.teams[0]
        assert team.error is not None
        assert team.error.status == 503


class TestComputeStatisticsById:
    """Test suite for compute_statistics with team IDs."""

    @patch("backend.stats._fetch_team_from_explorer_api")
    @patch("backend.stats.get_players_by_team")
    def test_compute_by_ids_success(self, mock_get_players, mock_fetch_info, monkeypatch):
        """Test successful computation with team IDs."""
        mock_fetch_info.return_value = TeamStats(
            team_id=39,
            team="Team Spirit",
            tag="TS",
            rating=2500.0,
            delta=25.0,
            logo_url="http://example.com/logo.png",
        )
        mock_get_players.return_value = (
            [Player(name="Player1", id=1)],
            [],
        )
        mock_task = MagicMock()
        monkeypatch.setattr("backend.dota_bet_analyzer.players_statistics_task", mock_task)

        result = compute_statistics(team_ids=[39])

        assert isinstance(result, StatsResponse)
        assert len(result.teams) == 1
        team = result.teams[0]
        assert team.team_id == 39
        # Verify fetch_info was called with team_id parameter
        mock_fetch_info.assert_called_once()
        call_kwargs = mock_fetch_info.call_args[1]
        assert call_kwargs.get("team_id") == 39
        assert call_kwargs.get("team_str") is None

    @patch("backend.stats._fetch_team_from_explorer_api")
    @patch("backend.stats.get_players_by_team")
    def test_compute_by_ids_multiple(self, mock_get_players, mock_fetch_info, monkeypatch):
        """Test computation with multiple team IDs."""
        mock_fetch_info.side_effect = [
            TeamStats(
                team_id=39,
                team="Team Spirit",
                tag="TS",
                rating=2500.0,
                delta=25.0,
            ),
            TeamStats(
                team_id=26,
                team="The Pango",
                tag="PG",
                rating=2400.0,
                delta=20.0,
            ),
        ]
        mock_get_players.return_value = ([], [])
        mock_task = MagicMock()
        monkeypatch.setattr("backend.dota_bet_analyzer.players_statistics_task", mock_task)

        result = compute_statistics(team_ids=[39, 26])

        assert len(result.teams) == 2
        assert result.teams[0].team_id == 39
        assert result.teams[1].team_id == 26

    def test_compute_by_ids_invalid_id(self):
        """Test error handling for invalid team IDs."""
        result = compute_statistics(team_ids=[-1])

        assert len(result.teams) == 1
        team = result.teams[0]
        assert team.error is not None
        assert team.error.message is not None
        assert "non-negative" in team.error.message.lower()

    def test_compute_by_ids_non_integer(self):
        """Test error handling when team_id is not an integer."""
        result = compute_statistics(team_ids=["39"])  # type: ignore

        assert len(result.teams) == 1
        team = result.teams[0]
        assert team.error is not None


class TestComputeStatisticsValidation:
    """Test suite for parameter validation."""

    @patch("backend.stats._fetch_team_from_explorer_api")
    @patch("backend.stats.get_players_by_team")
    def test_compute_with_both_teams_and_ids(self, mock_get_players, mock_fetch_info, monkeypatch):
        """Test that teams and team_ids can be provided together."""
        mock_fetch_info.side_effect = [
            TeamStats(
                team_id=39,
                team="Team Spirit",
                tag="TS",
                rating=2500.0,
                delta=25.0,
            ),
            TeamStats(
                team_id=123,
                team="Test Team",
                tag="TT",
                rating=2000.0,
                delta=15.0,
            ),
        ]
        mock_get_players.return_value = ([], [])
        mock_task = MagicMock()
        monkeypatch.setattr("backend.dota_bet_analyzer.players_statistics_task", mock_task)

        result = compute_statistics(teams=["Spirit"], team_ids=[123])

        assert len(result.teams) == 2
        assert result.teams[0].team == "Team Spirit"
        assert result.teams[1].team == "Test Team"

    def test_compute_missing_both_params(self):
        """Test that at least one parameter must be provided."""
        with pytest.raises(ValueError) as exc_info:
            compute_statistics()

        assert "must be provided" in str(exc_info.value).lower()

    def test_compute_both_params_empty_lists(self):
        """Test that empty lists don't satisfy the requirement."""
        with pytest.raises(ValueError) as exc_info:
            compute_statistics(teams=[], team_ids=[])

        assert "must be provided" in str(exc_info.value).lower()

    def test_compute_invalid_team_name(self):
        """Test error handling for invalid team name (empty string)."""
        result = compute_statistics(teams=[""])

        assert len(result.teams) == 1
        team = result.teams[0]
        assert team.error is not None
        assert team.error.code == "INVALID_TEAM_NAME"

    def test_compute_invalid_team_type(self):
        """Test error handling for non-string team names."""
        result = compute_statistics(teams=[None])  # type: ignore

        assert len(result.teams) == 1
        team = result.teams[0]
        assert team.error is not None


class TestComputeStatisticsErrorHandling:
    """Test suite for error handling in compute_statistics."""

    @patch("backend.stats._fetch_team_from_explorer_api")
    @patch("backend.stats.get_players_by_team")
    def test_compute_partial_failure(self, mock_get_players, mock_fetch_info, monkeypatch):
        """Test that one team's error doesn't prevent processing of others."""
        # First team succeeds
        error = ApiError(status=503, code="NETWORK_ERROR", message="Failed")
        mock_fetch_info.side_effect = [
            TeamStats(
                team_id=39,
                team="Team Spirit",
                tag="TS",
                rating=2500.0,
                delta=25.0,
            ),
            TeamStats(error=error, team="Failed"),  # Second team fails
        ]
        mock_get_players.return_value = ([], [])
        mock_task = MagicMock()
        monkeypatch.setattr("backend.dota_bet_analyzer.players_statistics_task", mock_task)

        result = compute_statistics(teams=["Spirit", "Failed"])

        assert len(result.teams) == 2
        assert result.teams[0].error is None
        assert result.teams[1].error is not None

    @patch("backend.stats._fetch_team_from_explorer_api")
    def test_compute_unexpected_exception(self, mock_fetch_info):
        """Test handling of unexpected exceptions during computation."""
        mock_fetch_info.side_effect = RuntimeError("Unexpected error")

        result = compute_statistics(teams=["Team"])

        assert len(result.teams) == 1
        team = result.teams[0]
        assert team.error is not None
        assert team.error.status == 500
        assert team.error.code == "UNEXPECTED_ERROR"

    @patch("backend.stats._fetch_team_from_explorer_api")
    def test_compute_fetch_stats_error(self, mock_fetch_info):
        """Test error handling when fetching team stats fails."""
        error = ApiError(status=502, code="HTTP_ERROR", message="API error")
        mock_fetch_info.return_value = TeamStats(
            team_id=39,
            team="Team",
            tag="T",
            rating=2500.0,
            delta=0.0,
            error=error,
        )

        result = compute_statistics(teams=["Team"])

        assert len(result.teams) == 1
        team = result.teams[0]
        assert team.error is not None
        assert team.error.status == 502


class TestComputeStatisticsTaskInitiation:
    """Test suite for Celery task initiation."""

    @patch("backend.stats._fetch_team_from_explorer_api")
    @patch("backend.stats.get_players_by_team")
    def test_compute_initiates_task_with_players(self, mock_get_players, mock_fetch_info, monkeypatch):
        """Test that task is initiated when team has players."""
        mock_fetch_info.return_value = TeamStats(
            team_id=39,
            team="Team Spirit",
            tag="TS",
            rating=2500.0,
            delta=25.0,
        )
        players = [Player(name="P1", id=100), Player(name="P2", id=200)]
        mock_get_players.return_value = (players, [])

        mock_task = MagicMock()
        mock_delay = MagicMock()
        mock_task.delay = mock_delay
        monkeypatch.setattr("backend.dota_bet_analyzer.players_statistics_task", mock_task)

        result = compute_statistics(teams=["Spirit"])

        team = result.teams[0]
        assert team.task_id is not None
        # Verify task.delay was called with correct account IDs
        mock_delay.assert_called_once()
        call_kwargs = mock_delay.call_args[1]
        assert set(call_kwargs["accounts"]) == {100, 200}

    @patch("backend.stats._fetch_team_from_explorer_api")
    @patch("backend.stats.get_players_by_team")
    def test_compute_no_task_without_players(self, mock_get_players, mock_fetch_info, monkeypatch):
        """Test that task is not initiated when team has no players."""
        mock_fetch_info.return_value = TeamStats(
            team_id=39,
            team="Team Spirit",
            tag="TS",
            rating=2500.0,
            delta=25.0,
        )
        mock_get_players.return_value = ([], [])  # No players

        mock_task = MagicMock()
        monkeypatch.setattr("backend.dota_bet_analyzer.players_statistics_task", mock_task)

        result = compute_statistics(teams=["Spirit"])

        team = result.teams[0]
        assert team.task_id is None
        mock_task.delay.assert_not_called()
