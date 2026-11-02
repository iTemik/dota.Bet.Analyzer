"""Celery tasks of the default queue (user work with progress): `players_statistics_task` for Compare.

Cache jobs of the background queue live in backend.jobs.
"""

import time

from backend.celery_app import celery
from backend.logging_config import setup_logging
from backend.opendota import OpenDotaError
from backend.stats import BAD_RANK_THRESHOLD, RankTally, get_team_matches_summary
from backend.task_store import (
    ProgressReporter,
    get_matches_cached,
    get_rank_cached,
    store_results,
)

logger = setup_logging(__name__)


@celery.task(bind=True)
def players_statistics_task(self, task_id, accounts: list[int], days: int = 20, rank_accounts: list[int] | None = None):
    """Celery task to fetch match statistics for multiple players.

    Saves one payload under `results:{task_id}` (read by GET /api/results/{task_id}, StatisticsResultSchema):
    - `summary`: team totals from get_team_matches_summary plus rank values; the only part the
      Team Comparison table reads (frontend getSummaryForTeam and the rows marked `summary: true`)
    - `results`: one entry per account with its match count and leaderboard rank, or its error
      (raw matches are not stored; the Team Insights table shows each player's rank from here).
      Accounts in `rank_accounts` get only `rank` (or `error`): they are not in `summary` or `successful`
    - `successful` / `total`: how many accounts were fetched; also sent in the final progress message

    Args:
        task_id: Unique task identifier for progress tracking
        accounts: List of account IDs to fetch statistics for
        days: Number of days of match history to fetch
        rank_accounts: Account IDs to fetch only the leaderboard rank for (stand-ins, no matches)
    """
    rank_accounts = rank_accounts or []
    progress = ProgressReporter(task_id, 2 + 2 * len(accounts) + len(rank_accounts))  # Initial + per-account + final
    try:
        logger.info(f"Starting players_statistics_task: task_id={task_id}, accounts={accounts}, days={days}")
        progress.start(f"Initializing match history fetch for {len(accounts)} players")

        results: list[dict[str, int | str | None]] = []  # Per player: match_count and rank, or the fetch error
        matches_stats = []  # List of lists: each inner list is matches for one player
        ranks = RankTally()
        for account_id in accounts:
            progress.next()

            def report_wait(delay: int, account_id: int = account_id) -> None:
                progress.waiting(delay, account_id)

            try:
                # Fetch match data for this account
                player_matches = get_matches_cached(account_id=account_id, days=days, on_wait=report_wait)
                matches_stats.append(player_matches)  # Append as a list per player

                # Only the count and rank are kept per player; the matches themselves feed `summary`
                result: dict[str, int | str | None] = {"account_id": account_id, "match_count": len(player_matches)}
                results.append(result)
                progress.report(
                    f"Fetched {len(player_matches)} matches for account {account_id}",
                    {"account_id": account_id, "match_count": len(player_matches)},
                )

                try:
                    player_rank = get_rank_cached(account_id, on_wait=report_wait)
                except OpenDotaError as e:
                    # The matches still count; the rank stays unknown and is asked again next time (not cached)
                    player_rank = None
                    logger.warning(f"Rank unavailable for account {account_id}: {e.message}")
                result["rank"] = player_rank
                ranks.add(player_rank)
                if player_rank is not None and player_rank > BAD_RANK_THRESHOLD:  # Tysyachniks ruin the games.
                    logger.info(f"Account {account_id} is tysyachnik and will ruin the games for high rank players")
                progress.report(
                    f"Got Player rank {player_rank} for account {account_id}",
                    {"account_id": account_id, "player_rank": player_rank},
                )

            except Exception as e:
                # Handle per-account errors gracefully
                # The player is left out of `summary`; the error stays visible in the results payload
                results.append({"account_id": account_id, "error": str(e)})
                progress.report(
                    f"Error fetching data for account {account_id}: {e!s}",
                    {"account_id": account_id, "error": str(e)},
                )

            time.sleep(0.01)  # Short sleep to prevent overwhelming the API

        summary = get_team_matches_summary(matches_stats)  # This is heavy logic. To check.
        summary.avg_rank = ranks.average
        summary.bad_rank_players = ranks.bad_rank_players

        successful = len([r for r in results if "error" not in r])

        for account_id in rank_accounts:
            progress.next()

            def report_wait(delay: int, account_id: int = account_id) -> None:
                progress.waiting(delay, account_id)

            try:
                player_rank = get_rank_cached(account_id, on_wait=report_wait)
                results.append({"account_id": account_id, "rank": player_rank})
                progress.report(
                    f"Got Player rank {player_rank} for account {account_id}",
                    {"account_id": account_id, "player_rank": player_rank},
                )
            except Exception as e:
                results.append({"account_id": account_id, "error": str(e)})
                progress.report(
                    f"Error fetching rank for account {account_id}: {e!s}",
                    {"account_id": account_id, "error": str(e)},
                )

            time.sleep(0.01)

        # Store heavy results separately (not in progress stream)
        store_results(
            task_id,
            {
                "results": results,
                "successful": successful,
                "total": len(accounts),
                "summary": summary.model_dump(),
            },
        )

        # Lightweight final message (no heavy data)
        progress.done(
            f"Completed: fetched data for {successful}/{len(accounts)} players",
            {"successful": successful, "total": len(accounts)},
        )

    except Exception as exc:
        logger.error(f"Task error for task_id={task_id}: {exc}", exc_info=True)
        progress.fail(exc)
        raise
