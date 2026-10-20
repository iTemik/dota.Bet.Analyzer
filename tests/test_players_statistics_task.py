"""Tests for players_statistics_task progress messages and results, and its helpers."""

from unittest.mock import patch

import pytest

from backend import dota_bet_analyzer, task_store
from backend.dota_bet_analyzer import players_statistics_task
from backend.stats import BAD_RANK_THRESHOLD, MatchesSummary, RankTally
from backend.task_store import ProgressReporter


def _run_task(accounts: list[int], ranks: dict[int, int | None], failing: set[int] | None = None):
    """Run the task with mocked data sources and return (progress calls, stored results)."""
    failing = failing or set()

    def fake_matches(account_id, days, on_wait=None):
        if account_id in failing:
            raise RuntimeError("boom")
        on_wait(5)
        return []

    def fake_rank(account_id, on_wait=None):
        return ranks.get(account_id)

    with (
        patch.object(task_store, "update_progress") as progress,
        patch.object(dota_bet_analyzer, "store_results") as store,
        patch.object(dota_bet_analyzer, "get_matches_cached", side_effect=fake_matches),
        patch.object(dota_bet_analyzer, "get_rank_cached", side_effect=fake_rank),
        patch.object(dota_bet_analyzer, "get_team_matches_summary", return_value=MatchesSummary()),
        patch.object(dota_bet_analyzer.time, "sleep"),
    ):
        players_statistics_task.run("t1", accounts, 20)
    return [c.args for c in progress.call_args_list], store.call_args.args[1]


def test_task_progress_messages_and_results():
    """Steps, percentages, messages and data match the original hand-written progress calls."""
    calls, results = _run_task([1, 2], {1: 100, 2: 1500}, failing=set())
    steps = 6
    assert calls == [
        ("t1", 0, "Initializing match history fetch for 2 players", 0.0, None),
        (
            "t1",
            1,
            "OpenDota limit reached, retrying account 1 in 5s",
            100 * (1 / steps),
            {"account_id": 1, "retry_in": 5},
        ),
        ("t1", 1, "Fetched 0 matches for account 1", 100 * (1 / steps), {"account_id": 1, "match_count": 0}),
        ("t1", 1, "Got Player rank 100 for account 1", 100 * (1 / steps), {"account_id": 1, "player_rank": 100}),
        (
            "t1",
            2,
            "OpenDota limit reached, retrying account 2 in 5s",
            100 * (2 / steps),
            {"account_id": 2, "retry_in": 5},
        ),
        ("t1", 2, "Fetched 0 matches for account 2", 100 * (2 / steps), {"account_id": 2, "match_count": 0}),
        ("t1", 2, "Got Player rank 1500 for account 2", 100 * (2 / steps), {"account_id": 2, "player_rank": 1500}),
        ("t1", steps, "Completed: fetched data for 2/2 players", 100, {"successful": 2, "total": 2}),
    ]
    assert results["results"] == [
        {"account_id": 1, "match_count": 0, "rank": 100},
        {"account_id": 2, "match_count": 0, "rank": 1500},
    ]
    assert results["successful"] == 2
    assert results["total"] == 2
    assert results["summary"]["avg_rank"] == 800.0
    assert results["summary"]["bad_rank_players"] == 1


def test_task_account_error_is_reported_and_skipped():
    """A failing account gets an error message and does not count as successful."""
    calls, results = _run_task([1, 2], {2: None}, failing={1})
    assert calls[1] == (
        "t1",
        1,
        "Error fetching data for account 1: boom",
        100 * (1 / 6),
        {"account_id": 1, "error": "boom"},
    )
    assert results["results"][0] == {"account_id": 1, "error": "boom"}
    assert results["results"][1] == {"account_id": 2, "match_count": 0, "rank": None}
    assert results["successful"] == 1
    assert results["summary"]["avg_rank"] == 0.0
    assert results["summary"]["bad_rank_players"] == 0


def test_task_error_reports_failure():
    """An unexpected error marks the task failed with progress -1 and re-raises."""
    with (
        patch.object(task_store, "update_progress") as progress,
        patch.object(dota_bet_analyzer, "get_team_matches_summary", side_effect=ValueError("bad")),
        pytest.raises(ValueError),
    ):
        players_statistics_task.run("t1", [], 20)
    assert progress.call_args.args == ("t1", -1, "Task error: bad", -1, {"error": True})


def test_progress_reporter_counts_steps():
    """next() advances the step; waiting() and fail() keep it; done() reports the last step."""
    with patch.object(task_store, "update_progress") as progress:
        reporter = ProgressReporter("t1", 4)
        reporter.start("start")
        reporter.next()
        reporter.report("one", {"a": 1})
        reporter.waiting(3, 42)
        reporter.done("finished")
        reporter.fail(RuntimeError("x"))
    assert [c.args for c in progress.call_args_list] == [
        ("t1", 0, "start", 0.0, None),
        ("t1", 1, "one", 25.0, {"a": 1}),
        ("t1", 1, "OpenDota limit reached, retrying account 42 in 3s", 25.0, {"account_id": 42, "retry_in": 3}),
        ("t1", 4, "finished", 100, None),
        ("t1", -1, "Task error: x", -1, {"error": True}),
    ]


def test_rank_tally_average_and_bad_ranks():
    """Unknown ranks are skipped; ranks above the threshold count as bad."""
    tally = RankTally()
    for rank in (None, 100, BAD_RANK_THRESHOLD, BAD_RANK_THRESHOLD + 1):
        tally.add(rank)
    assert tally.average == (100 + BAD_RANK_THRESHOLD + BAD_RANK_THRESHOLD + 1) / 3
    assert tally.bad_rank_players == 1
    assert RankTally().average == 0.0
