"""Prediction log routes: team snapshots, predictions and their head-to-head."""

from collections.abc import Callable

from flask import Response, jsonify

from backend.bookmakers import (
    OddsNotFound,
    find_odds,
    get_pari_series,
    get_winline_series,
)
from backend.head_to_head import get_head_to_head
from backend.helpers import Errors, api_error
from backend.logging_config import setup_logging
from backend.predictions import (
    SnapshotMissingError,
    create_prediction,
    delete_prediction,
    get_prediction,
    list_predictions,
    save_review,
    update_decision,
)
from backend.routes import ApiBlueprint
from backend.routes.catalog import full_version
from backend.schemas import (
    HeadToHeadSchema,
    OddsQuerySchema,
    OddsSchema,
    PredictionCreateSchema,
    PredictionDecisionSchema,
    PredictionDetailSchema,
    PredictionListQuerySchema,
    PredictionReviewSchema,
    PredictionSchema,
    SnapshotCreateSchema,
    SnapshotDetailSchema,
    SnapshotListQuerySchema,
    SnapshotSchema,
)
from backend.snapshots import get_snapshot, list_snapshots, save_snapshot

logger = setup_logging(__name__)


bp = ApiBlueprint(
    "Predictions", __name__, description="Prediction log: snapshots, predictions, head-to-head, bookmaker odds"
)


@bp.route("/snapshots", methods=["POST"])
@bp.arguments(SnapshotCreateSchema)
@bp.response(201, SnapshotSchema, description="New snapshot saved")
@bp.alt_response(200, schema=SnapshotSchema, description="Snapshot with the same key refreshed")
@bp.error_response(422, Errors.TEAM_ID_MISMATCH, "Invalid body, or team_id differs from team.team_id")
@bp.error_response(500, Errors.FAILED_TO_STORE_SNAPSHOT, "Database error")
def create_snapshot(args) -> tuple[Response, int]:
    """Save what the Compare page shows for one team.

    A snapshot is identified by team + UTC day + `days` + the team's latest league match (`team.latest_match_time`).
    Saving the same key again refreshes the stored data and returns 200; a new key returns 201. No OpenDota requests.
    """
    team_id = args["team_id"]
    if args["team"].get("team_id") not in (None, team_id):
        return api_error(422, Errors.TEAM_ID_MISMATCH, team_id=team_id, team_team_id=args["team"].get("team_id"))
    try:
        snapshot, created = save_snapshot(
            team_id, args["days"], args["team"], args["summary"], args["players"], full_version()
        )
        return jsonify(snapshot), 201 if created else 200
    except Exception as e:
        logger.error(f"Error storing snapshot for team {team_id}: {e}")
        return api_error(500, Errors.FAILED_TO_STORE_SNAPSHOT, e)


@bp.route("/snapshots", methods=["GET"])
@bp.arguments(SnapshotListQuerySchema, location="query")
@bp.response(200, SnapshotSchema(many=True))
@bp.error_response(422, Errors.VALIDATION_ERROR, "Invalid query parameters")
@bp.error_response(500, Errors.FAILED_TO_READ_SNAPSHOTS, "Database error")
def get_snapshots(args) -> tuple[Response, int]:
    """List saved team snapshots without their data, newest first.

    Filter by `team_id` and by UTC day with `from` and `to` (YYYY-MM-DD, inclusive).
    """
    try:
        snapshots = list_snapshots(args.get("team_id"), args.get("date_from"), args.get("date_to"))
        return jsonify(snapshots), 200
    except Exception as e:
        logger.error(f"Error listing snapshots: {e}")
        return api_error(500, Errors.FAILED_TO_READ_SNAPSHOTS, e)


@bp.route("/snapshots/<int:snapshot_id>", methods=["GET"])
@bp.response(200, SnapshotDetailSchema)
@bp.error_response(404, Errors.SNAPSHOT_NOT_FOUND, "Snapshot not found", snapshot_id=1)
@bp.error_response(500, Errors.FAILED_TO_READ_SNAPSHOTS, "Database error")
def get_snapshot_by_id(snapshot_id: int) -> tuple[Response, int]:
    """Get one saved team snapshot with its data (`team`, `summary`, `players`)."""
    try:
        snapshot = get_snapshot(snapshot_id)
    except Exception as e:
        logger.error(f"Error reading snapshot {snapshot_id}: {e}")
        return api_error(500, Errors.FAILED_TO_READ_SNAPSHOTS, e)
    if snapshot is None:
        return api_error(404, Errors.SNAPSHOT_NOT_FOUND, snapshot_id=snapshot_id)
    return jsonify(snapshot), 200


@bp.route("/predictions", methods=["POST"])
@bp.arguments(PredictionCreateSchema)
@bp.response(201, PredictionSchema, description="Prediction saved")
@bp.error_response(404, Errors.SNAPSHOT_NOT_FOUND, "Snapshot not found", snapshot_id=1)
@bp.error_response(422, Errors.VALIDATION_ERROR, "Invalid body")
@bp.error_response(500, Errors.FAILED_TO_STORE_PREDICTION, "Database error")
def post_prediction(args) -> tuple[Response, int]:
    """Save a series-win prediction made from two saved team snapshots.

    Both snapshots are locked from then on (saving their key again no longer refreshes them). Odds, `best_of`, bet
    and comment can be edited later with PUT. No OpenDota requests.
    """
    try:
        prediction = create_prediction(**args)
    except SnapshotMissingError as e:
        return api_error(404, Errors.SNAPSHOT_NOT_FOUND, snapshot_id=e.snapshot_id)
    except Exception as e:
        logger.error(f"Error storing prediction: {e}")
        return api_error(500, Errors.FAILED_TO_STORE_PREDICTION, e)
    return jsonify(prediction), 201


@bp.route("/predictions", methods=["GET"])
@bp.arguments(PredictionListQuerySchema, location="query")
@bp.response(200, PredictionSchema(many=True))
@bp.error_response(422, Errors.VALIDATION_ERROR, "Invalid query parameters")
@bp.error_response(500, Errors.FAILED_TO_READ_PREDICTIONS, "Database error")
def get_predictions(args) -> tuple[Response, int]:
    """List predictions, newest first, with team names and logos from their snapshots and computed `bet_won`.

    `status=pending` lists those without a result, `status=settled` those with one.
    """
    try:
        return jsonify(list_predictions(args.get("status"))), 200
    except Exception as e:
        logger.error(f"Error listing predictions: {e}")
        return api_error(500, Errors.FAILED_TO_READ_PREDICTIONS, e)


@bp.route("/predictions/<int:prediction_id>", methods=["GET"])
@bp.response(200, PredictionDetailSchema)
@bp.error_response(404, Errors.PREDICTION_NOT_FOUND, "Prediction not found", prediction_id=1)
@bp.error_response(500, Errors.FAILED_TO_READ_PREDICTIONS, "Database error")
def get_prediction_by_id(prediction_id: int) -> tuple[Response, int]:
    """Get one prediction with both snapshots and their data, for the review page."""
    try:
        prediction = get_prediction(prediction_id)
    except Exception as e:
        logger.error(f"Error reading prediction {prediction_id}: {e}")
        return api_error(500, Errors.FAILED_TO_READ_PREDICTIONS, e)
    if prediction is None:
        return api_error(404, Errors.PREDICTION_NOT_FOUND, prediction_id=prediction_id)
    return jsonify(prediction), 200


@bp.route("/predictions/<int:prediction_id>/head-to-head", methods=["GET"])
@bp.response(200, HeadToHeadSchema)
@bp.error_response(404, Errors.PREDICTION_NOT_FOUND, "Prediction not found", prediction_id=1)
@bp.error_response(500, Errors.FAILED_TO_READ_PREDICTIONS, "Database error")
def get_prediction_head_to_head(prediction_id: int) -> tuple[Response, int]:
    """League matches between the prediction's two teams, from `days` before the prediction up to now.

    Read from team 1's cached team matches: no OpenDota request while the cache is fresh, otherwise one.
    """
    try:
        head_to_head = get_head_to_head(prediction_id)
    except Exception as e:
        logger.error(f"Error reading head-to-head of prediction {prediction_id}: {e}")
        return api_error(500, Errors.FAILED_TO_READ_PREDICTIONS, e)
    if head_to_head is None:
        return api_error(404, Errors.PREDICTION_NOT_FOUND, prediction_id=prediction_id)
    return jsonify(head_to_head), 200


@bp.route("/predictions/<int:prediction_id>", methods=["PATCH"])
@bp.arguments(PredictionReviewSchema)
@bp.response(200, PredictionSchema, description="Review saved")
@bp.error_response(404, Errors.PREDICTION_NOT_FOUND, "Prediction not found", prediction_id=1)
@bp.error_response(422, Errors.INVALID_RESULT, "Invalid body, or the score does not fit best_of")
@bp.error_response(500, Errors.FAILED_TO_STORE_PREDICTION, "Database error")
def patch_prediction(args, prediction_id: int) -> tuple[Response, int]:
    """Save the review: the actual result as maps won by each team, and a review note.

    The score must be a finished series of the prediction's format (bo3: 2-0, 2-1, 1-2, 0-2, bo2: 2-0, 1-1, 0-2).
    With an unknown format any score with at least one map is accepted.
    Other fields (odds, bet, comment) are rejected, they are edited with PUT.
    """
    try:
        prediction = save_review(prediction_id, args["team1_maps_won"], args["team2_maps_won"], args.get("review_note"))
    except ValueError as e:
        return api_error(
            422,
            Errors.INVALID_RESULT,
            team1_maps_won=args["team1_maps_won"],
            team2_maps_won=args["team2_maps_won"],
            reason=str(e),
        )
    except Exception as e:
        logger.error(f"Error saving review of prediction {prediction_id}: {e}")
        return api_error(500, Errors.FAILED_TO_STORE_PREDICTION, e)
    if prediction is None:
        return api_error(404, Errors.PREDICTION_NOT_FOUND, prediction_id=prediction_id)
    return jsonify(prediction), 200


@bp.route("/predictions/<int:prediction_id>", methods=["PUT"])
@bp.arguments(PredictionDecisionSchema)
@bp.response(200, PredictionSchema, description="Prediction updated")
@bp.error_response(404, Errors.PREDICTION_NOT_FOUND, "Prediction not found", prediction_id=1)
@bp.error_response(422, Errors.INVALID_RESULT, "Invalid body, or the saved result does not fit the new best_of")
@bp.error_response(500, Errors.FAILED_TO_STORE_PREDICTION, "Database error")
def put_prediction(args, prediction_id: int) -> tuple[Response, int]:
    """Edit a saved prediction: odds, `best_of`, bet, stake and comment, all replaced together.

    The snapshots and the review stay. When a result is saved, the new `best_of` must still fit it.
    """
    try:
        prediction = update_decision(prediction_id, **args)
    except ValueError as e:
        return api_error(422, Errors.INVALID_RESULT, best_of=args["best_of"], reason=str(e))
    except Exception as e:
        logger.error(f"Error editing prediction {prediction_id}: {e}")
        return api_error(500, Errors.FAILED_TO_STORE_PREDICTION, e)
    if prediction is None:
        return api_error(404, Errors.PREDICTION_NOT_FOUND, prediction_id=prediction_id)
    return jsonify(prediction), 200


@bp.route("/predictions/<int:prediction_id>", methods=["DELETE"])
@bp.response(204, description="Prediction deleted, its snapshots stay")
@bp.error_response(404, Errors.PREDICTION_NOT_FOUND, "Prediction not found", prediction_id=1)
@bp.error_response(500, Errors.FAILED_TO_STORE_PREDICTION, "Database error")
def remove_prediction(prediction_id: int) -> tuple[Response, int] | tuple[str, int]:
    """Delete a prediction made by mistake. Its snapshots stay (and stay locked if another prediction uses them)."""
    try:
        deleted = delete_prediction(prediction_id)
    except Exception as e:
        logger.error(f"Error deleting prediction {prediction_id}: {e}")
        return api_error(500, Errors.FAILED_TO_STORE_PREDICTION, e)
    if not deleted:
        return api_error(404, Errors.PREDICTION_NOT_FOUND, prediction_id=prediction_id)
    return "", 204


if __name__ == "__main__":
    from backend import create_app

    app = create_app()
    app.run(debug=True)


def _odds_response(get_series: Callable[[], list[dict]], args: dict) -> tuple[Response, int]:
    """Odds of the two teams from a bookmaker's cached series, or the api_error for 404/503."""
    try:
        odds = find_odds(get_series(), (args["team1"], args["tag1"]), (args["team2"], args["tag2"]))
        return jsonify(odds), 200
    except OddsNotFound as e:
        return api_error(404, Errors.ODDS_NOT_FOUND, e, matches=e.matches)
    except ConnectionError as e:
        return api_error(503, Errors.FAILED_TO_FETCH_ODDS, e)


@bp.route("/odds/pari", methods=["GET"])
@bp.arguments(OddsQuerySchema, location="query")
@bp.response(200, OddsSchema)
@bp.error_response(404, Errors.ODDS_NOT_FOUND, "Pari has no upcoming series of these teams", matches=["A vs B"])
@bp.error_response(422, Errors.VALIDATION_ERROR, "Missing team name")
@bp.error_response(503, Errors.FAILED_TO_FETCH_ODDS, "The Pari line could not be loaded or read")
def get_pari_odds(args: dict) -> tuple[Response, int]:
    """Pari match-winner odds of the soonest series of two teams, for the prediction panel.

    One request to the Pari line at most every 5 minutes (the Dota 2 part is cached in Redis). Teams are matched
    by name or tag in either order; a 404 lists the series Pari has, to spot a differently spelled name.
    """
    return _odds_response(get_pari_series, args)


@bp.route("/odds/winline", methods=["GET"])
@bp.arguments(OddsQuerySchema, location="query")
@bp.response(200, OddsSchema)
@bp.error_response(404, Errors.ODDS_NOT_FOUND, "Winline has no upcoming series of these teams", matches=["A vs B"])
@bp.error_response(422, Errors.VALIDATION_ERROR, "Missing team name")
@bp.error_response(503, Errors.FAILED_TO_FETCH_ODDS, "The Winline line could not be loaded or read")
def get_winline_odds(args: dict) -> tuple[Response, int]:
    """Winline match-winner odds of the soonest series of two teams (prematch about 1-2 days ahead, and live).

    One short WebSocket session at most every 5 minutes (the Dota 2 part is cached in Redis). Teams are matched
    by name or tag in either order; a 404 lists the series Winline has.
    """
    return _odds_response(get_winline_series, args)
