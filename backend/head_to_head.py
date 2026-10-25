"""Head-to-head league matches between the two teams of a prediction.

Read from team 1's `/teams/{id}/matches` list, which the Compare page already loads and caches in d2ba.sqlite for
TEAM_MATCHES_TTL, so this costs no OpenDota request while the cache is fresh and one request otherwise.
"""

import time
from typing import Any, Optional

from backend.predictions import get_prediction
from backend.rosters import get_team_league_matches, window_start


def get_head_to_head(prediction_id: int, now: Optional[int] = None) -> Optional[dict[str, Any]]:
    """League matches between the prediction's teams, from `days` before the prediction up to now.

    Args:
        prediction_id: Prediction to read
        now: Current unix time (for tests)

    Returns:
        `since` (window start, unix seconds) and `matches` newest first, or None when the prediction does not exist
    """
    prediction = get_prediction(prediction_id)
    if prediction is None:
        return None
    created_at = prediction["created_at"]
    since = window_start(prediction["team1_snapshot"]["days"], created_at)
    team2_id = prediction["team2"]["team_id"]
    team1_matches = get_team_league_matches(
        prediction["team1"]["team_id"], now=now if now is not None else int(time.time())
    )
    matches = [
        {
            "match_id": m.match_id,
            "start_time": m.start_time,
            "team1_won": m.won,
            "before_prediction": m.start_time < created_at,
        }
        for m in team1_matches
        if m.opposing_team_id == team2_id and m.start_time >= since
    ]
    return {"since": since, "matches": matches}
