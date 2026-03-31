"""Test the _extract_players_from_rows function with various text inputs including Unicode.

This test suite verifies that the player extraction logic handles different character
encodings and text types correctly, including Chinese characters, emoji, and other
Unicode that previously caused logging errors.
"""

from typing import Any

from backend.pro_players import _extract_players_from_rows
from backend.stats import Player


class TestExtractPlayersFromRows:
    """Test suite for _extract_players_from_rows function."""

    def test_extract_basic_players(self) -> None:
        """Test extraction with basic ASCII player names."""
        rows: list[dict[str, Any]] = [
            {"account_id": 1, "name": "Player One", "is_pro": 1},
            {"account_id": 2, "name": "Player Two", "is_pro": 0},
            {"account_id": 3, "name": "Player Three", "is_pro": 1},
        ]

        pro_players, other_players = _extract_players_from_rows(rows)

        assert len(pro_players) == 2
        assert len(other_players) == 1
        assert pro_players[0].name == "Player One"
        assert pro_players[1].name == "Player Three"
        assert other_players[0].name == "Player Two"

    def test_extract_with_chinese_characters(self) -> None:
        """Test extraction with Chinese player names (the original error case)."""
        rows: list[dict[str, Any]] = [
            {"account_id": 171262902, "name": "医者watson`", "is_pro": 1},
            {"account_id": 171262903, "name": "职业选手", "is_pro": 1},
            {"account_id": 171262904, "name": "业余玩家", "is_pro": 0},
        ]

        pro_players, other_players = _extract_players_from_rows(rows)

        assert len(pro_players) == 2
        assert len(other_players) == 1
        assert pro_players[0].name == "医者watson`"
        assert pro_players[1].name == "职业选手"
        assert other_players[0].name == "业余玩家"

    def test_extract_with_emoji(self) -> None:
        """Test extraction with emoji in player names."""
        rows: list[dict[str, Any]] = [
            {"account_id": 1, "name": "🎮 Gaming Pro 🎮", "is_pro": 1},
            {"account_id": 2, "name": "🏆 Champion 🏆", "is_pro": 1},
            {"account_id": 3, "name": "🎯 Casual Player", "is_pro": 0},
        ]

        pro_players, other_players = _extract_players_from_rows(rows)

        assert len(pro_players) == 2
        assert len(other_players) == 1
        assert "🎮" in pro_players[0].name
        assert "🏆" in pro_players[1].name

    def test_extract_with_mixed_unicode(self) -> None:
        """Test extraction with mixed Unicode from different languages."""
        rows: list[dict[str, Any]] = [
            {"account_id": 1, "name": "Русский Игрок", "is_pro": 1},  # Russian
            {"account_id": 2, "name": "لاعب عربي", "is_pro": 1},  # Arabic
            {"account_id": 3, "name": "한국 선수", "is_pro": 0},  # Korean
            {"account_id": 4, "name": "日本の選手", "is_pro": 1},  # Japanese
            {"account_id": 5, "name": "Ελληνας παίκτης", "is_pro": 0},  # Greek
        ]

        pro_players, other_players = _extract_players_from_rows(rows)

        assert len(pro_players) == 3  # Russian, Arabic, Japanese
        assert len(other_players) == 2  # Korean, Greek
        assert pro_players[0].name == "Русский Игрок"
        assert pro_players[1].name == "لاعب عربي"
        assert pro_players[2].name == "日本の選手"

    def test_extract_empty_rows(self) -> None:
        """Test extraction with empty rows list."""
        rows: list[dict[str, Any]] = []

        pro_players, other_players = _extract_players_from_rows(rows)

        assert len(pro_players) == 0
        assert len(other_players) == 0

    def test_extract_skips_none_names(self) -> None:
        """Test that rows with None/empty names are skipped."""
        rows: list[dict[str, Any]] = [
            {"account_id": 1, "name": "Valid Player", "is_pro": 1},
            {"account_id": 2, "name": None, "is_pro": 1},  # Should be skipped
            {"account_id": 3, "name": "", "is_pro": 0},  # Should be skipped
            {"account_id": 4, "name": "Another Valid", "is_pro": 0},
        ]

        pro_players, other_players = _extract_players_from_rows(rows)

        assert len(pro_players) == 1
        assert len(other_players) == 1
        assert other_players[0].name == "Another Valid"

    def test_extract_preserves_account_id(self) -> None:
        """Test that account IDs are correctly preserved."""
        rows: list[dict[str, Any]] = [
            {"account_id": 12345, "name": "Pro Player", "is_pro": 1},
            {"account_id": 67890, "name": "Casual Player", "is_pro": 0},
        ]

        pro_players, other_players = _extract_players_from_rows(rows)

        assert pro_players[0].id == 12345
        assert other_players[0].id == 67890

    def test_extract_handles_is_pro_not_zero_or_one(self) -> None:
        """Test that is_pro values other than 1 are treated as 'other'."""
        rows: list[dict[str, Any]] = [
            {"account_id": 1, "name": "Player A", "is_pro": 1},  # Pro
            {"account_id": 2, "name": "Player B", "is_pro": 0},  # Other
            {"account_id": 3, "name": "Player C", "is_pro": 2},  # Other (not 1)
            {"account_id": 4, "name": "Player D", "is_pro": None},  # Other (None)
        ]

        pro_players, other_players = _extract_players_from_rows(rows)

        assert len(pro_players) == 1
        assert len(other_players) == 3
        assert pro_players[0].name == "Player A"

    def test_extract_with_special_characters(self) -> None:
        """Test extraction with special characters and symbols."""
        rows: list[dict[str, Any]] = [
            {"account_id": 1, "name": "Player@Name#1", "is_pro": 1},
            {"account_id": 2, "name": "Ñoño_Player", "is_pro": 1},
            {"account_id": 3, "name": "Café_Player", "is_pro": 0},
            {"account_id": 4, "name": "玩家™", "is_pro": 1},
        ]

        pro_players, other_players = _extract_players_from_rows(rows)

        assert len(pro_players) == 3
        assert len(other_players) == 1
        assert pro_players[2].name == "玩家™"

    def test_extract_returns_player_objects(self) -> None:
        """Test that returned items are Player objects with correct attributes."""
        rows: list[dict[str, Any]] = [
            {"account_id": 123, "name": "Test Player", "is_pro": 1},
        ]

        pro_players, other_players = _extract_players_from_rows(rows)

        assert len(pro_players) == 1
        assert isinstance(pro_players[0], Player)
        assert pro_players[0].name == "Test Player"
        assert pro_players[0].id == 123
        assert other_players == []

    def test_extract_returns_tuple(self) -> None:
        """Test that function returns a tuple of two lists."""
        rows: list[dict[str, Any]] = [
            {"account_id": 1, "name": "Player", "is_pro": 1},
        ]

        result = _extract_players_from_rows(rows)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], list)
        assert isinstance(result[1], list)
