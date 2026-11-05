"""Celery tasks of the default queue (user work with progress): `players_statistics_task` for Compare.

Cache jobs of the background queue live in backend.jobs.
"""

import time
from typing import Any, Optional

from backend.celery_app import celery
from backend.logging_config import setup_logging
from backend.meta import MetaParams, cached_hero_stats
from backend.opendota import OpenDotaError
from backend.stats import BAD_RANK_THRESHOLD, RankTally, get_team_matches_summary
from backend.task_store import (
    ProgressReporter,
    get_matches_cached,
    get_rank_cached,
    store_results,
)
from backend.team_meta import (
    TeamMetaParams,
    compute_team_meta,
    get_player_heroes_cached,
    player_heroes_days,
)

logger = setup_logging(__name__)


def _team_meta_step(progress: ProgressReporter, team_meta: dict[str, Any]) -> dict[str, Any]:
    """Fetch each core player's heroes (league + pubs, deeper and recent window) and compute the team meta state.

    One progress step per core player.

    Args:
        progress: The task's progress reporter
        team_meta: {"games": load_team_games output, "core": accounts, "meta_params", "params"} from
            compute_statistics

    Returns:
        compute_team_meta output, or {"error": message} when the hero stats are unavailable
    """
    games = team_meta["games"]
    days = player_heroes_days(games["deep_start"])
    recent_days = player_heroes_days(games["recent_start"])
    player_heroes: dict[int, Optional[dict[int, int]]] = {}
    player_heroes_recent: dict[int, Optional[dict[int, int]]] = {}
    for account_id in team_meta["core"]:
        progress.next()

        def report_wait(delay: int, account_id: int = account_id) -> None:
            progress.waiting(delay, account_id)

        try:
            player_heroes[account_id] = get_player_heroes_cached(account_id, days, on_wait=report_wait)
            progress.report(f"Got heroes of account {account_id}", {"account_id": account_id})
        except Exception as e:
            # Unknown practice: the player's league picks from the team games still count
            player_heroes[account_id] = None
            progress.report(
                f"Error fetching heroes for account {account_id}: {e!s}", {"account_id": account_id, "error": str(e)}
            )
        try:
            # Recent window only for the shown numbers; a failure leaves this player out of them
            player_heroes_recent[account_id] = get_player_heroes_cached(account_id, recent_days, on_wait=report_wait)
        except Exception as e:
            player_heroes_recent[account_id] = None
            logger.warning(f"Recent heroes unavailable for account {account_id}: {e}")
    try:
        hero_stats, _ = cached_hero_stats()
    except ConnectionError as e:
        logger.warning(f"Team meta skipped, hero stats unavailable: {e}")
        return {"error": str(e)}
    return compute_team_meta(
        games,
        team_meta["core"],
        player_heroes,
        hero_stats,
        MetaParams(**team_meta["meta_params"]),
        TeamMetaParams(**team_meta["params"]),
        player_heroes_recent,
    )


@celery.task(bind=True)
def players_statistics_task(
    self,
    task_id,
    accounts: list[int],
    days: int = 20,
    rank_accounts: list[int] | None = None,
    team_meta: dict[str, Any] | None = None,
):
    """Celery task to fetch match statistics for multiple players.

    Saves one payload under `results:{task_id}` (read by GET /api/results/{task_id}, StatisticsResultSchema):
    - `summary`: team totals from get_team_matches_summary plus rank values; the only part the
      Team Comparison table reads (frontend getSummaryForTeam and the rows marked `summary: true`)
    - `results`: one entry per account with its match count and leaderboard rank, or its error
      (raw matches are not stored; the Team Insights table shows each player's rank from here).
      Accounts in `rank_accounts` get only `rank` (or `error`): they are not in `summary` or `successful`
    - `successful` / `total`: how many accounts were fetched; also sent in the final progress message
    - `meta`: the team meta state (backend.team_meta.compute_team_meta), null without `team_meta`;
      {"error": message} when the hero stats were unavailable

    Args:
        task_id: Unique task identifier for progress tracking
        accounts: List of account IDs to fetch statistics for
        days: Number of days of match history to fetch
        rank_accounts: Account IDs to fetch only the leaderboard rank for (stand-ins, no matches)
        team_meta: Input of the team meta state from compute_statistics (see _team_meta_step); None skips it
    """
    rank_accounts = rank_accounts or []
    meta_steps = len(team_meta["core"]) if team_meta else 0
    # Initial + per-account + heroes per core player + final
    progress = ProgressReporter(task_id, 2 + 2 * len(accounts) + len(rank_accounts) + meta_steps)
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

        meta = _team_meta_step(progress, team_meta) if team_meta else None

        # Store heavy results separately (not in progress stream)
        store_results(
            task_id,
            {
                "results": results,
                "successful": successful,
                "total": len(accounts),
                "summary": summary.model_dump(),
                "meta": meta,
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
