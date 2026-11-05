"""Marshmallow schemas for API request/response validation and OpenAPI documentation.

Note: For models that have corresponding Pydantic classes (e.g., StatsResponse, TeamStats),
the schemas are derived from the Pydantic models to ensure they stay in sync.
Any changes to the Pydantic models will automatically reflect in the API documentation.
"""

from typing import Any

from marshmallow import Schema, ValidationError, fields, validate, validates_schema
from pydantic import BaseModel

# Import Pydantic models for auto-generation (imported here to avoid circular imports later)
from backend.meta import MetaParams
from backend.models import Player, StatsResponse, TeamStats
from backend.stats import ApiError
from backend.team_meta import TeamMetaParams

# Cache for generated schemas to avoid duplicates
_schema_cache: dict[type[BaseModel], type[Schema]] = {}


def pydantic_to_marshmallow_field(field_info, field_type) -> fields.Field:  # noqa: C901
    """Convert Pydantic field to Marshmallow field.

    Args:
        field_info: Pydantic field info
        field_type: Python type annotation

    Returns:
        Marshmallow field instance
    """
    from typing import Union, get_args, get_origin

    is_required = field_info.is_required()

    # Handle Optional types (which are Union[T, None])
    origin = get_origin(field_type)
    if origin is Union:
        args = get_args(field_type)
        if type(None) in args:
            # It's Optional[T] - unwrap and handle the inner type
            # For Optional fields, we want them to allow None and not be required
            inner_type = next(arg for arg in args if arg is not type(None))

            # Recursively process the inner type, but force it to be optional
            # We create the field directly since we know it should allow_none
            inner_origin = get_origin(inner_type)

            # Handle Optional[List[...]]
            if inner_origin is list:
                list_inner_type = get_args(inner_type)[0]
                if isinstance(list_inner_type, type) and issubclass(list_inner_type, BaseModel):
                    nested_schema = pydantic_to_marshmallow(list_inner_type)
                    return fields.List(fields.Nested(nested_schema), allow_none=True, required=False)
                else:
                    list_inner_field = _make_field_for_type(list_inner_type)
                    return fields.List(list_inner_field, allow_none=True, required=False)

            # Handle Optional[dict]
            elif inner_origin is dict:
                return fields.Dict(keys=fields.Str(), values=fields.Raw(), allow_none=True, required=False)

            # Handle Optional[BaseModel]
            elif isinstance(inner_type, type) and issubclass(inner_type, BaseModel):
                nested_schema = pydantic_to_marshmallow(inner_type)
                # Add example metadata for better OpenAPI documentation
                example = None
                if inner_type.__name__ == "ApiError":
                    example = {
                        "status": 503,
                        "code": "NETWORK_ERROR",
                        "message": "Failed to fetch data",
                        "details": {"url": "/api/url"},
                    }
                metadata = {"example": example} if example else {}
                # Use dump_default=None together with allow_none=True so Optional nested models
                # accept explicit null values while still producing a clean OpenAPI spec.
                return fields.Nested(
                    nested_schema,
                    required=False,
                    allow_none=True,
                    dump_default=None,
                    load_default=None,
                    metadata=metadata,
                )

            # Handle Optional[basic types]
            else:
                return _make_field_for_type(inner_type, allow_none=True)

    # Handle List types
    if origin is list:
        inner_type = get_args(field_type)[0]
        # Check if inner type is a BaseModel
        if isinstance(inner_type, type) and issubclass(inner_type, BaseModel):
            nested_schema = pydantic_to_marshmallow(inner_type)
            if is_required:
                return fields.List(fields.Nested(nested_schema))
            else:
                return fields.List(fields.Nested(nested_schema), load_default=list)
        else:
            list_inner_field = _make_field_for_type(inner_type)
            if is_required:
                return fields.List(list_inner_field)
            else:
                return fields.List(list_inner_field, load_default=list)

    # Handle dict types
    if origin is dict:
        if is_required:
            return fields.Dict(keys=fields.Str(), values=fields.Raw())
        else:
            return fields.Dict(keys=fields.Str(), values=fields.Raw(), load_default=dict)

    # Handle nested Pydantic models
    if isinstance(field_type, type) and issubclass(field_type, BaseModel):
        nested_schema = pydantic_to_marshmallow(field_type)
        return fields.Nested(nested_schema, required=is_required)

    # Handle basic types
    return _make_field_for_type(field_type, required=is_required)


def _make_field_for_type(field_type, required=False, allow_none=False, load_default=None) -> fields.Field:
    """Create a Marshmallow field for a basic Python type.

    Args:
        field_type: Python type (str, int, float, bool, dict)
        required: Whether the field is required
        allow_none: Whether the field allows None values
        load_default: Default value when loading

    Returns:
        Marshmallow field instance
    """
    kwargs: dict[str, Any] = {}
    if allow_none:
        kwargs["allow_none"] = True
        kwargs["required"] = False
        # Don't set load_default when allow_none is True
    elif load_default is not None:
        kwargs["load_default"] = load_default
    else:
        kwargs["required"] = required

    # Use explicit type checks for proper type inference
    if field_type is str:
        return fields.Str(**kwargs)
    elif field_type is int:
        return fields.Int(**kwargs)
    elif field_type is float:
        return fields.Float(**kwargs)
    elif field_type is bool:
        return fields.Bool(**kwargs)
    elif field_type is dict:
        return fields.Dict(keys=fields.Str(), values=fields.Raw(), **kwargs)
    else:
        return fields.Raw(**kwargs)


def pydantic_to_marshmallow(pydantic_model: type[BaseModel], name: str | None = None) -> type[Schema]:
    """Auto-generate Marshmallow schema from Pydantic model.

    This ensures schemas stay synchronized with Pydantic models automatically.
    Uses caching to avoid creating duplicate schemas for the same Pydantic model.

    Args:
        pydantic_model: Pydantic model class
        name: Optional schema name override (defaults to ModelName + 'Schema')

    Returns:
        Marshmallow Schema class

    Example:
        >>> from backend.stats import StatsResponse
        >>> StatsResponseSchema = pydantic_to_marshmallow(StatsResponse)
    """
    # Check cache first to avoid creating duplicate schemas
    if pydantic_model in _schema_cache:
        return _schema_cache[pydantic_model]

    schema_name = name or f"{pydantic_model.__name__}Schema"
    schema_attrs: dict[str, any] = {}  # type: ignore[valid-type]

    # Add docstring from Pydantic model
    if pydantic_model.__doc__:
        schema_attrs["__doc__"] = pydantic_model.__doc__

    # Convert Pydantic fields to Marshmallow fields
    for field_name, field_info in pydantic_model.model_fields.items():
        field_type = field_info.annotation
        marshmallow_field = pydantic_to_marshmallow_field(field_info, field_type)

        # Add description from Pydantic field if available
        if field_info.description:
            # Build new metadata dict by combining existing metadata with description
            existing_metadata = dict(marshmallow_field.metadata) if marshmallow_field.metadata else {}
            existing_metadata["description"] = field_info.description
            # Create new field instance with updated metadata
            marshmallow_field.metadata = existing_metadata

        schema_attrs[field_name] = marshmallow_field

    # Create Meta class for ordered fields (optional but nice for consistent output)
    MetaClass = type("Meta", (), {"ordered": True})
    schema_attrs["Meta"] = MetaClass  # type: ignore[assignment]

    schema_class = type(schema_name, (Schema,), schema_attrs)  # type: ignore[return-value]

    # Cache the generated schema
    _schema_cache[pydantic_model] = schema_class

    return schema_class


class VersionSchema(Schema):
    """Version information response schema."""

    class Meta:
        """Schema metadata with example."""

        ordered = True

    backend = fields.Str(
        required=True, metadata={"description": "Backend version (MAJOR.MINOR.BUILD)", "example": "0.7.DEV"}
    )
    build = fields.Str(required=True, metadata={"description": "Build number", "example": "DEV"})


class MetaThresholdsSchema(Schema):
    """Meta tab thresholds as query parameters (defaults in backend.meta.MetaParams)."""

    pro_min_pick_ban = fields.Float(
        load_default=MetaParams.pro_min_pick_ban,
        validate=validate.Range(min=0, max=100),
        metadata={"description": "Pro meta: minimum pick + ban rate in pro matches, percent"},
    )
    ultra_min_win = fields.Float(
        load_default=MetaParams.ultra_min_win,
        validate=validate.Range(min=0, max=100),
        metadata={"description": "Ultra meta: minimum pro win rate, percent"},
    )
    ultra_min_picks = fields.Int(
        load_default=MetaParams.ultra_min_picks,
        validate=validate.Range(min=1),
        metadata={"description": "Ultra meta: minimum pro picks"},
    )
    pub_top = fields.Int(
        load_default=MetaParams.pub_top,
        validate=validate.Range(min=1, max=200),
        metadata={"description": "Pub meta: number of most picked Immortal + Divine + Ancient heroes"},
    )
    pub_min_win = fields.Float(
        load_default=MetaParams.pub_min_win,
        validate=validate.Range(min=0, max=100),
        metadata={"description": "Pub meta: minimum win rate of those heroes, percent"},
    )


class TeamMetaQuerySchema(MetaThresholdsSchema):
    """Team meta state windows and thresholds as query parameters (defaults in backend.team_meta.TeamMetaParams)."""

    deep_days = fields.Int(
        load_default=TeamMetaParams.deep_days,
        validate=validate.Range(min=1, max=365),
        metadata={"description": "Team meta: deeper window in days (the recent window is `days`)"},
    )
    sample_games = fields.Int(
        load_default=TeamMetaParams.sample_games,
        validate=validate.Range(min=1, max=100),
        metadata={"description": "Team meta: newest league games the states are computed from"},
    )
    sample_min_games = fields.Int(
        load_default=TeamMetaParams.sample_min_games,
        validate=validate.Range(min=1, max=100),
        metadata={"description": "Team meta: fewer games give players_know or no_info (players' heroes fetched)"},
    )
    actively_meta2_pct = fields.Float(
        load_default=TeamMetaParams.actively_meta2_pct,
        validate=validate.Range(min=0, max=100),
        metadata={"description": "Team meta: actively needs more games with 2+ meta heroes than this percent"},
    )
    actively_meta3_pct = fields.Float(
        load_default=TeamMetaParams.actively_meta3_pct,
        validate=validate.Range(min=0, max=100),
        metadata={"description": "Team meta: actively also needs more games with 3+ meta heroes than this percent"},
    )
    plays_meta2_pct = fields.Float(
        load_default=TeamMetaParams.plays_meta2_pct,
        validate=validate.Range(min=0, max=100),
        metadata={"description": "Team meta: doesn't play at or below this percent of games with 2+ meta heroes"},
    )
    plays_meta3_pct = fields.Float(
        load_default=TeamMetaParams.plays_meta3_pct,
        validate=validate.Range(min=0, max=100),
        metadata={"description": "Team meta: doesn't play at or below this percent of games with 3+ meta heroes"},
    )
    pool_narrow_heroes = fields.Int(
        load_default=TeamMetaParams.pool_narrow_heroes,
        validate=validate.Range(min=1),
        metadata={"description": "Hero pool: narrow with fewer different heroes in a full sample"},
    )
    pool_wide_heroes = fields.Int(
        load_default=TeamMetaParams.pool_wide_heroes,
        validate=validate.Range(min=1),
        metadata={"description": "Hero pool: wide with more different heroes in a full sample"},
    )
    practice_league_games = fields.Int(
        load_default=TeamMetaParams.practice_league_games,
        validate=validate.Range(min=1),
        metadata={"description": "Team meta: league games on a hero that prove a player's practice"},
    )
    practice_total_games = fields.Int(
        load_default=TeamMetaParams.practice_total_games,
        validate=validate.Range(min=1),
        metadata={"description": "Team meta: league + pub games on a hero that prove a player's practice"},
    )
    players_know_min = fields.Int(
        load_default=TeamMetaParams.players_know_min,
        validate=validate.Range(min=1, max=5),
        metadata={"description": "Team meta: core players practising a meta hero for players know meta"},
    )
    meta_hero_min_games = fields.Int(
        load_default=TeamMetaParams.meta_hero_min_games,
        validate=validate.Range(min=1),
        metadata={"description": "Team meta: team picks a meta hero needs to be listed"},
    )
    patch_cut = fields.Bool(
        load_default=TeamMetaParams.patch_cut,
        metadata={"description": "Team meta: windows start no earlier than the latest patch"},
    )


class TeamStatisticsQuerySchema(TeamMetaQuerySchema):
    """Query parameters for team statistics endpoint (team meta thresholds included)."""

    days = fields.Int(
        load_default=20,
        validate=validate.Range(min=1, max=365),
        metadata={
            "description": (
                "Window in days for the roster (latest league matches) and player match history (default: 20)"
            )
        },
    )

    team = fields.List(
        fields.Str(),
        required=False,
        validate=validate.Length(min=1, max=10),
        metadata={
            "description": (
                "Team names to analyze (1-10 teams combined with team_ids). "
                "Can be specified multiple times: `?team=Alpha&team=Beta`. "
                "Both team and team_id parameters can be used together; combined count must not exceed 10."
            )
        },
    )
    team_id = fields.List(
        fields.Int(),
        required=False,
        validate=validate.Length(min=1, max=10),
        metadata={
            "description": (
                "Team IDs to analyze (1-10 teams combined with team names). "
                "Can be specified multiple times: `?team_id=123&team_id=456`. "
                "Both team and team_id parameters can be used together; combined count must not exceed 10."
            )
        },
    )


class PlayerStatisticsQuerySchema(Schema):
    """Query parameters for player statistics endpoint."""

    account_id = fields.List(
        fields.Int(),
        required=True,
        validate=validate.Length(min=1, max=10),
        metadata={"description": "List of player account IDs (1-10 players)"},
    )
    days = fields.Int(
        load_default=20,
        validate=validate.Range(min=1, max=365),
        metadata={"description": "Number of days to analyze (default: 20)"},
    )


class TaskResponseSchema(Schema):
    """Task creation response schema."""

    task_id = fields.Str(required=True, metadata={"description": "Unique task identifier"})
    status = fields.Str(required=True, metadata={"description": "Task status"})


class TeamSchema(Schema):
    """Team information schema."""

    team_id = fields.Int(required=True, metadata={"description": "Unique team identifier"})
    name = fields.Str(required=True, metadata={"description": "Team name"})
    tag = fields.Str(allow_none=True, metadata={"description": "Team tag/abbreviation"})
    logo_url = fields.Str(allow_none=True, metadata={"description": "URL to team logo"})
    rating = fields.Float(allow_none=True, metadata={"description": "Team rating"})
    last_match_time = fields.Int(allow_none=True, metadata={"description": "Unix timestamp of last match"})


class TeamSearchQuerySchema(Schema):
    """Query parameters for team search endpoint."""

    q = fields.Str(
        required=True,
        validate=validate.Length(min=2),
        metadata={"description": "Search query (minimum 2 characters)"},
    )
    limit = fields.Int(
        load_default=10,
        validate=validate.Range(min=1, max=50),
        metadata={"description": "Maximum number of results (default: 10, max: 50)"},
    )


class JobRunQuerySchema(Schema):
    """Query parameters of POST /jobs/{name}/run."""

    full = fields.Bool(
        load_default=False,
        metadata={
            "description": "Teams job only: fetch every OpenDota /teams page, not only teams with new league games"
        },
    )


class JobSchema(Schema):
    """Status of one background cache job."""

    name = fields.Str(required=True, metadata={"description": "Job name, e.g. teams"})
    title = fields.Str(required=True, metadata={"description": "Name shown to the user, e.g. Teams list"})
    state = fields.Str(
        required=True,
        validate=validate.OneOf(["idle", "queued", "running", "failed"]),
        metadata={"description": "idle (not queued or running), queued, running, or failed (last run failed)"},
    )
    progress = fields.Float(required=True, metadata={"description": "Progress of the current or last run, 0-100"})
    message = fields.Str(
        required=True, allow_none=True, metadata={"description": "Status or result of the current or last run"}
    )
    last_success = fields.Int(
        required=True, allow_none=True, metadata={"description": "Unix time of the last successful run"}
    )
    last_error = fields.Str(required=True, allow_none=True, metadata={"description": "Error of the last failed run"})
    last_error_at = fields.Int(
        required=True, allow_none=True, metadata={"description": "Unix time of the last failed run"}
    )
    next_run = fields.Int(
        required=True,
        allow_none=True,
        metadata={"description": "Unix time when the job is due again; null when it is due now"},
    )


class HeroSchema(Schema):
    """Hero from the OpenDota hero list."""

    hero_id = fields.Int(required=True, metadata={"description": "OpenDota hero id"})
    name = fields.Str(required=True, metadata={"description": "Internal name, e.g. npc_dota_hero_antimage"})
    localized_name = fields.Str(required=True, metadata={"description": "Display name, e.g. Anti-Mage"})
    icon = fields.Str(required=True, metadata={"description": "Full URL of the hero icon"})


class PlayerResultSchema(Schema):
    """Schema for individual player result entry."""

    account_id = fields.Int(required=True, metadata={"description": "Player account ID"})
    match_count = fields.Int(metadata={"description": "Number of matches fetched for this player"})
    rank = fields.Int(
        allow_none=True, metadata={"description": "Leaderboard rank, null when the player is not on the leaderboard"}
    )
    error = fields.Str(metadata={"description": "Error message if player data fetch failed"})


class MatchesSummarySchema(Schema):
    """Schema for match collection summary statistics."""

    rating_matches = fields.Int(load_default=0, metadata={"description": "Number of rating matches (ranked games)"})
    tournament_matches = fields.Int(
        load_default=0, metadata={"description": "Number of lobby matches (league games and scrims)"}
    )
    other_matches = fields.Int(load_default=0, metadata={"description": "Number of other matches"})
    matches_median = fields.Float(allow_none=True, metadata={"description": "Median number of matches per player"})
    matches_avg = fields.Float(allow_none=True, metadata={"description": "Average number of matches per player"})
    win_percentage = fields.Float(allow_none=True, metadata={"description": "Team win percentage across all matches"})
    rating_win_percentage = fields.Float(
        allow_none=True, metadata={"description": "Win percentage in rating (pub) matches only"}
    )
    tournament_win_percentage = fields.Float(
        allow_none=True, metadata={"description": "Win percentage in lobby matches (league games and scrims)"}
    )
    avg_rank = fields.Float(allow_none=True, metadata={"description": "Average player rank"})
    bad_rank_players = fields.Int(allow_none=True, metadata={"description": "Number of players with rank > 1000"})


class TeamMetaWindowSchema(Schema):
    """Team games and hero pool in one window (recent = `days`, deep = `deep_days`)."""

    start = fields.Int(required=True, metadata={"description": "Window start (unix seconds), cut at the patch"})
    games = fields.Int(required=True, metadata={"description": "League games with all five picks known"})
    heroes = fields.Int(metadata={"description": "Different heroes the team picked (hero pool size, any hero)"})


class TeamMetaSampleSchema(TeamMetaWindowSchema):
    """The newest `sample_games` league games the states come from."""

    meta2_games_pct = fields.Float(allow_none=True, metadata={"description": "Games with 2+ meta heroes, percent"})
    meta3_games_pct = fields.Float(allow_none=True, metadata={"description": "Games with 3+ meta heroes, percent"})
    meta_picks_pct = fields.Float(
        allow_none=True, metadata={"description": "Team picks that are meta heroes, percent (stand-ins included)"}
    )

    start = fields.Int(allow_none=True, metadata={"description": "Start time of the oldest game in the sample"})
    window = fields.Str(metadata={"description": "recent when the recent window had enough games, else deep"})


class TeamMetaHeroSchema(Schema):
    """A meta hero the team picked or a core player practises."""

    hero_id = fields.Int(required=True, metadata={"description": "OpenDota hero id"})
    localized_name = fields.Str(required=True, metadata={"description": "Display name"})
    icon = fields.Str(required=True, metadata={"description": "Full URL of the hero icon"})
    ultra = fields.Bool(required=True, metadata={"description": "Ultra meta hero"})
    games = fields.Int(required=True, metadata={"description": "Team picks in the deep window (recent included)"})
    recent_games = fields.Int(required=True, metadata={"description": "Team picks in the recent window"})
    practice_players = fields.Int(
        required=True, metadata={"description": "Core players who practise the hero (league or league + pub games)"}
    )


class TeamMetaPlayerSchema(Schema):
    """A core player's practised meta heroes."""

    account_id = fields.Int(required=True, metadata={"description": "Player account ID"})
    meta_heroes = fields.List(fields.Int(), required=True, metadata={"description": "Practised meta hero ids"})
    pub_known = fields.Bool(
        required=True, metadata={"description": "False when the player's league + pub heroes could not be fetched"}
    )


class TeamMetaSchema(Schema):
    """Does the team play the meta heroes (backend.team_meta.compute_team_meta)."""

    state = fields.Str(
        metadata={"description": "actively, tries, players_know, doesnt_play or no_info"}, required=False
    )
    pool_state = fields.Str(
        allow_none=True, metadata={"description": "Hero pool: narrow, normal or wide; null without a full sample"}
    )
    sample = fields.Nested(TeamMetaSampleSchema)
    patch = fields.Str(allow_none=True, metadata={"description": "Latest patch the windows are cut at"})
    recent = fields.Nested(TeamMetaWindowSchema)
    deep = fields.Nested(TeamMetaWindowSchema)
    pro_meta_picks_pct = fields.Float(
        allow_none=True, metadata={"description": "Share of all pro picks on meta heroes, percent (pro avg)"}
    )
    meta_heroes_total = fields.Int(metadata={"description": "Number of meta heroes (pro and ultra) checked"})
    heroes = fields.List(
        fields.Nested(TeamMetaHeroSchema),
        metadata={"description": "Meta heroes picked `meta_hero_min_games`+ times, most team picks first"},
    )
    players = fields.List(fields.Nested(TeamMetaPlayerSchema))
    params = fields.Dict(metadata={"description": "Team meta windows and thresholds used"})
    error = fields.Str(metadata={"description": "Set instead of the rest when the hero stats were unavailable"})


class StatisticsResultSchema(Schema):
    """Complete statistics computation result schema.

    This is the final result structure returned by /api/results/<task_id>
    after the background task completes. The Team Comparison table reads only `summary`;
    `results` lists each player's match count or error (no raw matches).
    """

    results = fields.List(
        fields.Nested(PlayerResultSchema),
        required=True,
        metadata={"description": "List of per-player results (may include errors for failed fetches)"},
    )
    successful = fields.Int(required=True, metadata={"description": "Number of players successfully fetched"})
    total = fields.Int(required=True, metadata={"description": "Total number of players requested"})
    summary = fields.Nested(
        MatchesSummarySchema, required=True, metadata={"description": "Aggregated match statistics across all players"}
    )
    meta = fields.Nested(
        TeamMetaSchema, allow_none=True, metadata={"description": "Team meta state; null for a task without a team"}
    )


class SnapshotPlayerSchema(Schema):
    """A player's numbers in a snapshot, from /api/results results[] (Team Insights reads the rank)."""

    account_id = fields.Int(required=True, metadata={"description": "Player account ID"})
    rank = fields.Int(allow_none=True, load_default=None, metadata={"description": "Leaderboard rank, null if none"})
    match_count = fields.Int(
        allow_none=True, load_default=None, metadata={"description": "Matches fetched for the player"}
    )


class SnapshotCreateSchema(Schema):
    """Body of POST /api/snapshots: what the Compare page shows for one team."""

    team_id = fields.Int(required=True, validate=validate.Range(min=1), metadata={"description": "Team ID"})
    days = fields.Int(
        required=True,
        validate=validate.Range(min=1, max=365),
        metadata={"description": "Statistics window the data was computed with"},
    )
    team = fields.Dict(
        required=True,
        metadata={"description": "The team entry of GET /api/statistics teams[] as shown (task_id is dropped)"},
    )
    summary = fields.Dict(
        allow_none=True,
        load_default=None,
        metadata={"description": "summary of GET /api/results/{task_id}, null when it was not available"},
    )
    players = fields.List(
        fields.Nested(SnapshotPlayerSchema),
        load_default=list,
        metadata={"description": "Per player rank and match count from GET /api/results/{task_id} results[]"},
    )


class SnapshotListQuerySchema(Schema):
    """Query parameters of GET /api/snapshots."""

    team_id = fields.Int(metadata={"description": "Only this team's snapshots"})
    date_from = fields.Date(data_key="from", metadata={"description": "Only snapshots from this UTC day (YYYY-MM-DD)"})
    date_to = fields.Date(data_key="to", metadata={"description": "Only snapshots up to this UTC day (inclusive)"})


class SnapshotSchema(Schema):
    """A saved team snapshot, without its data."""

    class Meta:
        """Keep fields in declaration order."""

        ordered = True

    snapshot_id = fields.Int(required=True, metadata={"description": "Snapshot ID"})
    team_id = fields.Int(required=True, metadata={"description": "Team ID"})
    team_name = fields.Str(allow_none=True, metadata={"description": "Team name at the time of the snapshot"})
    snapshot_date = fields.Str(required=True, metadata={"description": "UTC day of the snapshot (YYYY-MM-DD)"})
    days = fields.Int(required=True, metadata={"description": "Statistics window the data was computed with"})
    last_match_time = fields.Int(
        required=True, metadata={"description": "Team's latest league match in the window (unix seconds), 0 if none"}
    )
    taken_at = fields.Int(required=True, metadata={"description": "When the data was saved or last refreshed (unix)"})
    app_version = fields.Str(required=True, metadata={"description": "Backend version that saved the data"})


class SnapshotDetailSchema(SnapshotSchema):
    """A saved team snapshot with its data."""

    data = fields.Dict(
        required=True, metadata={"description": "Saved data: `team`, `summary` and `players` as sent when saving"}
    )


class PredictionDecisionSchema(Schema):
    """Body of PUT /api/predictions/{id}: the bookmaker values and the decision, all replaced together."""

    team1_odds = fields.Float(
        required=True,
        validate=validate.Range(min=1, min_inclusive=False),
        metadata={"description": "Bookmaker decimal coefficient for team 1, above 1"},
    )
    team2_odds = fields.Float(
        required=True,
        validate=validate.Range(min=1, min_inclusive=False),
        metadata={"description": "Bookmaker decimal coefficient for team 2, above 1"},
    )
    best_of = fields.Int(
        allow_none=True,
        load_default=None,
        validate=validate.OneOf([1, 2, 3, 5]),
        metadata={"description": "Series format: 1, 2, 3 or 5, null when unknown (n/a)"},
    )
    bet_team = fields.Int(
        allow_none=True,
        load_default=None,
        validate=validate.OneOf([1, 2]),
        metadata={"description": "Team bet on to win the series (1 or 2), null for a prediction without a bet"},
    )
    stake = fields.Float(
        allow_none=True,
        load_default=None,
        validate=validate.Range(min=0, min_inclusive=False),
        metadata={"description": "Amount bet, only with bet_team"},
    )
    comment = fields.Str(load_default="", metadata={"description": "Reasoning written before the match"})

    @validates_schema
    def validate_bet(self, data: dict, **kwargs) -> None:
        """Reject a stake without a bet."""
        if data.get("stake") is not None and data.get("bet_team") is None:
            raise ValidationError("stake needs bet_team", field_name="stake")


class PredictionCreateSchema(PredictionDecisionSchema):
    """Body of POST /api/predictions: a series-win prediction made from two saved team snapshots."""

    team1_snapshot_id = fields.Int(required=True, metadata={"description": "Snapshot of team 1 (POST /api/snapshots)"})
    team2_snapshot_id = fields.Int(required=True, metadata={"description": "Snapshot of team 2 (POST /api/snapshots)"})

    @validates_schema
    def validate_snapshots(self, data: dict, **kwargs) -> None:
        """Reject one snapshot used for both teams."""
        if data["team1_snapshot_id"] == data["team2_snapshot_id"]:
            raise ValidationError("team1 and team2 need different snapshots", field_name="team2_snapshot_id")


class PredictionListQuerySchema(Schema):
    """Query parameters of GET /api/predictions."""

    status = fields.Str(
        validate=validate.OneOf(["pending", "settled"]),
        metadata={"description": "pending: no result yet, settled: result entered. All when omitted"},
    )


class PredictionReviewSchema(Schema):
    """Body of PATCH /api/predictions/{id}: the review. Odds, bet and comment are edited with PUT."""

    team1_maps_won = fields.Int(required=True, metadata={"description": "Maps won by team 1"})
    team2_maps_won = fields.Int(required=True, metadata={"description": "Maps won by team 2"})
    review_note = fields.Str(
        allow_none=True, load_default=None, metadata={"description": "Thoughts after the match, omitted keeps it"}
    )


class PredictionTeamSchema(Schema):
    """A team of a prediction as saved in its snapshot."""

    class Meta:
        """Keep fields in declaration order."""

        ordered = True

    snapshot_id = fields.Int(required=True, metadata={"description": "Snapshot the prediction was made from"})
    team_id = fields.Int(required=True, metadata={"description": "Team ID"})
    name = fields.Str(allow_none=True, metadata={"description": "Team name at the time of the snapshot"})
    tag = fields.Str(allow_none=True, metadata={"description": "Team tag at the time of the snapshot"})
    logo_url = fields.Str(allow_none=True, metadata={"description": "Team logo at the time of the snapshot"})


class PredictionSchema(Schema):
    """A saved prediction with its computed bet outcome."""

    class Meta:
        """Keep fields in declaration order."""

        ordered = True

    prediction_id = fields.Int(required=True, metadata={"description": "Prediction ID"})
    created_at = fields.Int(required=True, metadata={"description": "When it was saved (unix seconds)"})
    team1 = fields.Nested(PredictionTeamSchema, required=True)
    team2 = fields.Nested(PredictionTeamSchema, required=True)
    team1_odds = fields.Float(required=True, metadata={"description": "Bookmaker coefficient for team 1"})
    team2_odds = fields.Float(required=True, metadata={"description": "Bookmaker coefficient for team 2"})
    best_of = fields.Int(allow_none=True, metadata={"description": "Series format: 1, 2, 3 or 5, null when unknown"})
    bet_team = fields.Int(allow_none=True, metadata={"description": "Team bet on (1 or 2), null without a bet"})
    stake = fields.Float(allow_none=True, metadata={"description": "Amount bet, null if not given"})
    comment = fields.Str(required=True, metadata={"description": "Reasoning written before the match"})
    team1_maps_won = fields.Int(allow_none=True, metadata={"description": "Maps won by team 1, null until reviewed"})
    team2_maps_won = fields.Int(allow_none=True, metadata={"description": "Maps won by team 2, null until reviewed"})
    review_note = fields.Str(allow_none=True, metadata={"description": "Thoughts after the match"})
    bet_won = fields.Bool(
        allow_none=True,
        metadata={"description": "Whether the bet team won the series (a bo2 draw loses), null if pending or no bet"},
    )


class PredictionDetailSchema(PredictionSchema):
    """A saved prediction with both snapshots and their data."""

    team1_snapshot = fields.Nested(SnapshotDetailSchema, required=True)
    team2_snapshot = fields.Nested(SnapshotDetailSchema, required=True)


class HeadToHeadMatchSchema(Schema):
    """One league match between the two teams of a prediction."""

    class Meta:
        """Keep fields in declaration order."""

        ordered = True

    match_id = fields.Int(required=True, metadata={"description": "OpenDota match ID"})
    start_time = fields.Int(required=True, metadata={"description": "Match start (unix seconds)"})
    team1_won = fields.Bool(allow_none=True, metadata={"description": "Whether team 1 won, null if unknown"})
    before_prediction = fields.Bool(required=True, metadata={"description": "Played before the prediction was saved"})


class HeadToHeadSchema(Schema):
    """League matches between the two teams of a prediction, newest first."""

    class Meta:
        """Keep fields in declaration order."""

        ordered = True

    since = fields.Int(required=True, metadata={"description": "Window start: `days` before the prediction"})
    matches = fields.List(fields.Nested(HeadToHeadMatchSchema), required=True)


class MatchTeamSchema(Schema):
    """A team of a Liquipedia series, linked to the teams table by name when possible."""

    class Meta:
        """Keep fields in declaration order."""

        ordered = True

    name = fields.Str(required=True, metadata={"description": "Team name on Liquipedia"})
    team_id = fields.Int(allow_none=True, metadata={"description": "OpenDota team ID, null if the name is not known"})
    logo_url = fields.Str(allow_none=True, metadata={"description": "Team logo from the teams table, null if unknown"})


class MatchTournamentSchema(Schema):
    """Tournament of a Liquipedia series."""

    class Meta:
        """Keep fields in declaration order."""

        ordered = True

    name = fields.Str(required=True, metadata={"description": "Tournament name, with the stage but no day"})
    url = fields.Str(allow_none=True, metadata={"description": "Tournament page on Liquipedia, null if not linked"})
    icon = fields.Str(allow_none=True, metadata={"description": "Tournament icon on Liquipedia, null if none"})


class MatchSchema(Schema):
    """One upcoming or finished series."""

    class Meta:
        """Keep fields in declaration order."""

        ordered = True

    start_time = fields.Int(required=True, metadata={"description": "Series start (unix seconds)"})
    best_of = fields.Int(allow_none=True, metadata={"description": "Number of maps (Bo1/2/3/5), null if not shown"})
    team1 = fields.Nested(MatchTeamSchema, required=True)
    team2 = fields.Nested(MatchTeamSchema, required=True)
    tournament = fields.Nested(
        MatchTournamentSchema, allow_none=True, metadata={"description": "Tournament, null if not shown"}
    )
    score1 = fields.Int(allow_none=True, metadata={"description": "Maps won by team 1 (finished series only)"})
    score2 = fields.Int(allow_none=True, metadata={"description": "Maps won by team 2 (finished series only)"})


class MatchesSchema(Schema):
    """Upcoming series soonest first and finished series newest first."""

    class Meta:
        """Keep fields in declaration order."""

        ordered = True

    upcoming = fields.List(fields.Nested(MatchSchema), required=True)
    finished = fields.List(fields.Nested(MatchSchema), required=True)


class OddsQuerySchema(Schema):
    """Query parameters of GET /api/odds/pari: the two teams as the prediction panel shows them."""

    team1 = fields.Str(required=True, validate=validate.Length(min=1), metadata={"description": "Team 1 name"})
    team2 = fields.Str(required=True, validate=validate.Length(min=1), metadata={"description": "Team 2 name"})
    tag1 = fields.Str(load_default=None, metadata={"description": "Team 1 tag, also matched"})
    tag2 = fields.Str(load_default=None, metadata={"description": "Team 2 tag, also matched"})


class OddsSchema(Schema):
    """Match-winner odds of the soonest series of the two teams, in the requested team order."""

    class Meta:
        """Keep fields in declaration order."""

        ordered = True

    team1_odds = fields.Float(required=True, metadata={"description": "Decimal odds of team 1 winning the series"})
    team2_odds = fields.Float(required=True, metadata={"description": "Decimal odds of team 2 winning the series"})
    start_time = fields.Int(allow_none=True, metadata={"description": "Series start (unix seconds)"})
    tournament = fields.Str(required=True, metadata={"description": "Tournament as the bookmaker names it"})
    live = fields.Bool(required=True, metadata={"description": "The series has already started"})
    names = fields.List(fields.Str(), required=True, metadata={"description": "Team names at the bookmaker"})


# Auto-generated schemas from Pydantic models
# These are generated at module import time to ensure they stay in sync with Pydantic models
# If you modify the Pydantic models (Player, TeamStats, StatsResponse), these schemas
# will automatically reflect those changes.

# Generate schemas from Pydantic models
ErrorSchema = pydantic_to_marshmallow(ApiError)
PlayerSchema = pydantic_to_marshmallow(Player)
TeamStatsSchema = pydantic_to_marshmallow(TeamStats)
StatsResponseSchema = pydantic_to_marshmallow(StatsResponse)


class MetaQuerySchema(MetaThresholdsSchema):
    """Query parameters of GET /api/heroes/meta (thresholds; defaults in backend.meta.MetaParams)."""

    refresh = fields.Bool(
        load_default=False,
        metadata={
            "description": "Fetch new hero stats from OpenDota instead of the 1 hour cache (at most once a minute)"
        },
    )


class MetaHeroSchema(Schema):
    """Hero in at least one meta, with its pro and pub stats."""

    class Meta:
        """Keep fields in declaration order."""

        ordered = True

    hero_id = fields.Int(required=True, metadata={"description": "OpenDota hero id"})
    localized_name = fields.Str(required=True, metadata={"description": "Display name"})
    icon = fields.Str(required=True, metadata={"description": "Full URL of the hero icon"})
    meta = fields.List(
        fields.Str(), required=True, metadata={"description": 'Metas the hero is in: "ultra", "pro", "pub"'}
    )
    pro_picks = fields.Int(required=True, metadata={"description": "Pro picks"})
    pro_bans = fields.Int(required=True, metadata={"description": "Pro bans"})
    pro_wins = fields.Int(required=True, metadata={"description": "Pro wins"})
    pro_pick_ban_rate = fields.Float(
        allow_none=True, metadata={"description": "(picks + bans) / pro matches, percent; null without pro matches"}
    )
    pro_win_rate = fields.Float(
        allow_none=True, metadata={"description": "Pro wins / picks, percent; null without picks"}
    )
    pub_picks = fields.Int(required=True, metadata={"description": "Immortal + Divine + Ancient picks"})
    pub_wins = fields.Int(required=True, metadata={"description": "Immortal + Divine + Ancient wins"})
    pub_pick_rate = fields.Float(allow_none=True, metadata={"description": "Pub picks / matches, percent"})
    pub_win_rate = fields.Float(
        allow_none=True, metadata={"description": "Pub wins / picks, percent; null without picks"}
    )


class MetaSchema(Schema):
    """Current hero meta from OpenDota /heroStats (OpenDota's window, about the last 7 days)."""

    class Meta:
        """Keep fields in declaration order."""

        ordered = True

    fetched_at = fields.Int(required=True, metadata={"description": "When the hero stats were fetched (unix seconds)"})
    patch = fields.Str(allow_none=True, metadata={"description": "Latest Dota patch, null when unknown"})
    params = fields.Dict(required=True, metadata={"description": "Thresholds used"})
    pro_matches = fields.Int(required=True, metadata={"description": "Pro matches in the window (pro picks / 10)"})
    pub_matches = fields.Int(
        required=True, metadata={"description": "Immortal + Divine + Ancient matches (picks / 10)"}
    )
    heroes = fields.List(
        fields.Nested(MetaHeroSchema),
        required=True,
        metadata={"description": "Heroes in any meta: ultra first, then pro, then pub only"},
    )
