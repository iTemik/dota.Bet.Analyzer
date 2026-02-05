"""Tests for helper functions in backend.helpers module."""

import pytest

from backend.helpers import build_explorer_query


class TestBuildExplorerQuery:
    """Test suite for build_explorer_query function."""

    def test_prepare_sql_by_team_name(self):
        """Test SQL generation for team name search."""
        sql = build_explorer_query(team="Alpha")

        # Should contain name/tag filtering with ILIKE
        assert "ILIKE" in sql
        assert "Alpha" in sql
        assert "t.name ILIKE" in sql or "t.tag ILIKE" in sql
        # Should include LEFT JOIN for rating
        assert "LEFT JOIN team_rating" in sql
        # Should order by rating for name-based search
        assert "ORDER BY tr.rating DESC" in sql

    def test_prepare_sql_by_team_id(self):
        """Test SQL generation for team ID search."""
        sql = build_explorer_query(team_id=123)

        # Should use direct ID lookup
        assert "t.team_id = 123" in sql
        # Should NOT use ILIKE for ID-based search
        assert "ILIKE" not in sql
        # Should NOT order by rating for ID-based search
        assert "ORDER BY" not in sql or "tr.rating" not in sql

    def test_prepare_sql_escapes_single_quotes(self):
        """Test that single quotes in team names are properly escaped."""
        sql = build_explorer_query(team="Team's Name")

        # Should escape single quotes as ''
        assert "Team''s Name" in sql
        # Should not have unescaped quotes that could cause SQL injection
        assert sql.count("'") % 2 == 0  # Even number of single quotes

    def test_prepare_sql_escapes_backslashes(self):
        """Test that backslashes in team names are properly escaped."""
        sql = build_explorer_query(team="Team\\Name")

        # Should escape backslash
        assert "Team\\\\Name" in sql

    def test_prepare_sql_mutually_exclusive_params(self):
        """Test that both team and team_id cannot be provided together."""
        with pytest.raises(ValueError) as exc_info:
            build_explorer_query(team="Alpha", team_id=123)

        assert "mutually exclusive" in str(exc_info.value).lower() or "not both" in str(exc_info.value).lower()

    def test_prepare_sql_missing_both_params(self):
        """Test that at least one parameter must be provided."""
        with pytest.raises(ValueError) as exc_info:
            build_explorer_query()

        assert "must be provided" in str(exc_info.value).lower()

    def test_prepare_sql_invalid_team_name_none(self):
        """Test that None team name is invalid."""
        with pytest.raises(ValueError):
            build_explorer_query(team=None, team_id=None)

    def test_prepare_sql_invalid_team_name_empty_string(self):
        """Test that empty string team name is invalid."""
        with pytest.raises(ValueError) as exc_info:
            build_explorer_query(team="")

        assert "invalid" in str(exc_info.value).lower()

    def test_prepare_sql_invalid_team_id_negative(self):
        """Test that negative team ID is invalid."""
        with pytest.raises(ValueError) as exc_info:
            build_explorer_query(team_id=-1)

        assert "invalid" in str(exc_info.value).lower()

    def test_prepare_sql_valid_team_id_zero(self):
        """Test that team_id=0 is valid (non-negative integer)."""
        sql = build_explorer_query(team_id=0)
        assert "t.team_id = 0" in sql

    def test_prepare_sql_includes_rating_and_delta(self):
        """Test that SQL selects rating and delta fields."""
        sql = build_explorer_query(team="Test")

        assert "tr.rating" in sql
        assert "tr.delta" in sql

    def test_prepare_sql_by_name_contains_filter(self):
        """Test that name-based search uses LIKE for both name and tag."""
        sql = build_explorer_query(team="G2")

        # Should check both name and tag
        assert "t.name ILIKE" in sql
        assert "t.tag ILIKE" in sql
        # Should have OR between them
        assert "OR" in sql

    def test_prepare_sql_limit_clause(self):
        """Test that LIMIT 1 is included in queries."""
        sql_by_name = build_explorer_query(team="Alpha")
        sql_by_id = build_explorer_query(team_id=123)

        assert "LIMIT 1" in sql_by_name
        assert "LIMIT 1" in sql_by_id

    def test_prepare_sql_selects_correct_fields(self):
        """Test that SQL selects all required fields."""
        sql = build_explorer_query(team="Test")

        required_fields = ["t.team_id", "t.name", "t.tag", "tr.rating", "tr.delta"]
        for field in required_fields:
            assert field in sql
