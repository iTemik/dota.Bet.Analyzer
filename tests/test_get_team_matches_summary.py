"""Tests for get_team_matches_summary function."""

import pytest

from backend.stats import MatchesSummary, MatchStats, get_team_matches_summary


class TestGetTeamMatchesSummary:
    """Test cases for get_team_matches_summary function."""

    def test_empty_input_no_players(self):
        """Test with empty input (no players)."""
        result = get_team_matches_summary([])

        assert isinstance(result, MatchesSummary)
        assert result.rating_matches == 0
        assert result.tournament_matches == 0
        assert result.other_matches == 0
        assert result.matches_avg == 0.0
        assert result.matches_median == 0.0
        assert result.win_percentage == 0.0  # no matches = 0%

    def test_single_player_all_rating_matches(self):
        """Test single player with all rating matches.

        Rating matches: game_mode in [1, 3, 4, 22] AND lobby_type in [0, 4, 5, 6, 7, 9, 22]
        """
        matches = [
            MatchStats(match_id=1, player_slot=0, radiant_win=True, game_mode=22, lobby_type=0, hero_id=1),
            MatchStats(match_id=2, player_slot=1, radiant_win=False, game_mode=4, lobby_type=5, hero_id=2),
            MatchStats(match_id=3, player_slot=0, radiant_win=True, game_mode=1, lobby_type=9, hero_id=3),
            MatchStats(match_id=4, player_slot=0, radiant_win=True, game_mode=3, lobby_type=4, hero_id=4),
        ]

        result = get_team_matches_summary([matches])

        assert result.rating_matches == 4
        assert result.tournament_matches == 0
        assert result.other_matches == 0
        assert result.matches_avg == 4.0
        assert result.matches_median == 4.0
        assert result.win_percentage == 75.0  # 3 wins out of 4 matches

    def test_single_player_all_tournament_matches(self):
        """Test single player with all tournament matches.

        Tournament matches: game_mode in [2] AND lobby_type in [1, 2]
        """
        matches = [
            MatchStats(match_id=1, player_slot=0, radiant_win=True, game_mode=2, lobby_type=1, hero_id=1),
            MatchStats(match_id=2, player_slot=1, radiant_win=False, game_mode=2, lobby_type=2, hero_id=2),
        ]

        result = get_team_matches_summary([matches])

        assert result.rating_matches == 0
        assert result.tournament_matches == 2
        assert result.other_matches == 0
        assert result.matches_avg == 2.0
        assert result.matches_median == 2.0
        assert result.win_percentage == 50.0  # 1 win out of 2 matches

    def test_single_player_mixed_matches(self):
        """Test single player with mixed match types."""
        matches = [
            # Rating match: game_mode=4, lobby_type=0
            MatchStats(match_id=1, player_slot=0, radiant_win=True, game_mode=4, lobby_type=0, hero_id=1),
            # Tournament match: game_mode=2, lobby_type=1
            MatchStats(match_id=2, player_slot=1, radiant_win=False, game_mode=2, lobby_type=1, hero_id=2),
            # Other match: game_mode=1, lobby_type=2 (game_mode=1 is rating but lobby_type=2 is tournament)
            MatchStats(match_id=3, player_slot=0, radiant_win=True, game_mode=1, lobby_type=2, hero_id=3),
            # Rating match: game_mode=22, lobby_type=4
            MatchStats(match_id=4, player_slot=1, radiant_win=False, game_mode=22, lobby_type=4, hero_id=4),
        ]

        result = get_team_matches_summary([matches])

        assert result.rating_matches == 2
        assert result.tournament_matches == 1
        assert result.other_matches == 1
        assert result.matches_avg == 4.0
        assert result.matches_median == 4.0
        assert result.win_percentage == 50.0  # 2 wins out of 4 matches

    def test_two_players_with_different_match_counts(self):
        """Test two players with different match counts (tests median calculation)."""
        # Player 1: 5 rating matches
        player1_matches = [
            MatchStats(match_id=i, player_slot=0, radiant_win=True, game_mode=4, lobby_type=0, hero_id=1)
            for i in range(1, 6)
        ]

        # Player 2: 3 tournament matches
        player2_matches = [
            MatchStats(match_id=i, player_slot=1, radiant_win=False, game_mode=2, lobby_type=1, hero_id=2)
            for i in range(6, 9)
        ]

        result = get_team_matches_summary([player1_matches, player2_matches])

        assert result.rating_matches == 5
        assert result.tournament_matches == 3
        assert result.other_matches == 0
        assert result.matches_avg == 4.0  # (5 + 3) / 2
        assert result.matches_median == 4.0  # median of [5, 3]
        assert result.win_percentage == 62.5  # 5 wins out of 8 matches

    def test_three_players_median_odd_count(self):
        """Test three players for median calculation with odd number of counts."""
        # Player 1: 2 rating matches
        player1 = [
            MatchStats(match_id=1, player_slot=0, radiant_win=True, game_mode=4, lobby_type=0, hero_id=1),
            MatchStats(match_id=2, player_slot=0, radiant_win=True, game_mode=4, lobby_type=0, hero_id=1),
        ]

        # Player 2: 5 tournament matches
        player2 = [
            MatchStats(match_id=i, player_slot=1, radiant_win=False, game_mode=2, lobby_type=1, hero_id=2)
            for i in range(3, 8)
        ]

        # Player 3: 3 other matches
        player3 = [
            MatchStats(match_id=i, player_slot=2, radiant_win=True, game_mode=5, lobby_type=3, hero_id=3)
            for i in range(8, 11)
        ]

        result = get_team_matches_summary([player1, player2, player3])

        assert result.matches_avg == pytest.approx((2 + 5 + 3) / 3, rel=1e-6)  # ≈ 3.333
        assert result.matches_median == 3.0  # median of [2, 5, 3] is 3
        assert result.win_percentage == 50.0  # 5 wins out of 10 matches

    def test_four_players_median_even_count(self):
        """Test four players for median calculation with even number of counts."""
        # Player 1: 1 rating match
        player1 = [
            MatchStats(match_id=1, player_slot=0, radiant_win=True, game_mode=4, lobby_type=0, hero_id=1),
        ]

        # Player 2: 2 tournament matches
        player2 = [
            MatchStats(match_id=i, player_slot=1, radiant_win=False, game_mode=2, lobby_type=1, hero_id=2)
            for i in range(2, 4)
        ]

        # Player 3: 3 rating matches
        player3 = [
            MatchStats(match_id=i, player_slot=2, radiant_win=True, game_mode=1, lobby_type=4, hero_id=3)
            for i in range(4, 7)
        ]

        # Player 4: 4 other matches
        player4 = [
            MatchStats(match_id=i, player_slot=3, radiant_win=False, game_mode=5, lobby_type=3, hero_id=4)
            for i in range(7, 11)
        ]

        result = get_team_matches_summary([player1, player2, player3, player4])

        assert result.matches_avg == 2.5  # (1 + 2 + 3 + 4) / 4
        assert result.matches_median == 2.5  # median of [1, 2, 3, 4] is (2 + 3) / 2
        assert result.win_percentage == 40.0  # 4 wins out of 10 matches

    def test_players_with_empty_match_lists(self):
        """Test with players having empty match lists."""
        # Player 1: 2 rating matches
        player1 = [
            MatchStats(match_id=1, player_slot=0, radiant_win=True, game_mode=4, lobby_type=0, hero_id=1),
            MatchStats(match_id=2, player_slot=0, radiant_win=True, game_mode=4, lobby_type=0, hero_id=1),
        ]

        # Player 2: 0 matches
        player2 = []

        # Player 3: 3 tournament matches
        player3 = [
            MatchStats(match_id=i, player_slot=2, radiant_win=True, game_mode=2, lobby_type=1, hero_id=3)
            for i in range(3, 6)
        ]

        result = get_team_matches_summary([player1, player2, player3])

        assert result.rating_matches == 2
        assert result.tournament_matches == 3
        assert result.other_matches == 0
        assert result.matches_avg == pytest.approx((2 + 0 + 3) / 3, rel=1e-6)  # ≈ 1.667
        assert result.matches_median == 2.0  # median of [2, 0, 3] is 2
        assert result.win_percentage == 100.0  # 5 wins out of 5 matches (player1: 2 wins, player3: 3 wins)

    def test_match_categorization_accuracy(self):
        """Test that matches are correctly categorized by game_mode and lobby_type.

        Using the actual constants:
        - GAME_MODE_RATING = [1, 3, 4, 22]
        - GAME_MODE_TOURNAMENT = [2]
        - LOBBY_TYPE_RATING = [0, 4, 5, 6, 7, 9, 22]
        - LOBBY_TYPE_TOURNAMENT = [1, 2]
        """
        matches = [
            # Rating match: game_mode=4, lobby_type=0
            MatchStats(match_id=1, player_slot=0, radiant_win=True, game_mode=4, lobby_type=0, hero_id=1),
            # Rating match: game_mode=22, lobby_type=9
            MatchStats(match_id=2, player_slot=0, radiant_win=True, game_mode=22, lobby_type=9, hero_id=1),
            # Rating match: game_mode=3, lobby_type=5 (new game_mode value)
            MatchStats(match_id=3, player_slot=0, radiant_win=True, game_mode=3, lobby_type=5, hero_id=1),
            # Tournament match: game_mode=2, lobby_type=1
            MatchStats(match_id=4, player_slot=1, radiant_win=False, game_mode=2, lobby_type=1, hero_id=2),
            # Other: game_mode=5, lobby_type=2 (no valid game_mode for rating or tournament)
            MatchStats(match_id=5, player_slot=0, radiant_win=True, game_mode=5, lobby_type=2, hero_id=3),
            # Other: game_mode=4, lobby_type=3 (game_mode=4 is rating but lobby_type=3 is not in rating list)
            MatchStats(match_id=6, player_slot=1, radiant_win=False, game_mode=4, lobby_type=3, hero_id=4),
            # Other: game_mode=2, lobby_type=0 (game_mode=2 is tournament but lobby_type=0 is not in tournament list)
            MatchStats(match_id=7, player_slot=0, radiant_win=True, game_mode=2, lobby_type=0, hero_id=5),
        ]

        result = get_team_matches_summary([matches])

        assert result.rating_matches == 3
        assert result.tournament_matches == 1
        assert result.other_matches == 3
        assert result.matches_avg == 7.0
        assert result.matches_median == 7.0
        assert result.win_percentage == pytest.approx(71.43, rel=1e-2)  # 5 wins out of 7 matches

    def test_large_number_of_players(self):
        """Test with a large number of players."""
        # Create 10 players with varying numbers of rating matches
        matches_by_player = []
        for i in range(10):
            player_matches = [
                MatchStats(match_id=j, player_slot=i, radiant_win=j % 2 == 0, game_mode=4, lobby_type=0, hero_id=1)
                for j in range(i + 1)  # Player i has i+1 matches
            ]
            matches_by_player.append(player_matches)

        result = get_team_matches_summary(matches_by_player)

        # Total matches: 1 + 2 + 3 + ... + 10 = 55
        assert result.rating_matches == 55
        assert result.tournament_matches == 0
        assert result.other_matches == 0
        assert result.matches_avg == 5.5  # 55 / 10
        assert result.matches_median == 5.5  # median of [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        assert result.win_percentage == pytest.approx(54.55, rel=1e-2)  # 30 wins out of 55

    def test_all_constants_in_use(self):
        """Test using all values from the constants."""
        matches = [
            # GAME_MODE_RATING values with LOBBY_TYPE_RATING values
            MatchStats(match_id=1, player_slot=0, radiant_win=True, game_mode=1, lobby_type=0, hero_id=1),
            MatchStats(match_id=2, player_slot=0, radiant_win=True, game_mode=3, lobby_type=4, hero_id=1),
            MatchStats(match_id=3, player_slot=0, radiant_win=True, game_mode=4, lobby_type=6, hero_id=1),
            MatchStats(match_id=4, player_slot=0, radiant_win=True, game_mode=22, lobby_type=22, hero_id=1),
            # GAME_MODE_TOURNAMENT with LOBBY_TYPE_TOURNAMENT
            MatchStats(match_id=5, player_slot=1, radiant_win=False, game_mode=2, lobby_type=1, hero_id=2),
            MatchStats(match_id=6, player_slot=1, radiant_win=False, game_mode=2, lobby_type=2, hero_id=2),
        ]

        result = get_team_matches_summary([matches])

        assert result.rating_matches == 4
        assert result.tournament_matches == 2
        assert result.other_matches == 0
        assert result.matches_avg == 6.0
        assert result.matches_median == 6.0
        assert result.win_percentage == pytest.approx(66.67, rel=1e-2)  # 4 wins out of 6 matches
