"""Marshmallow schemas for API request/response validation and OpenAPI documentation.

Note: For models that have corresponding Pydantic classes (e.g., StatsResponse, TeamStats),
the schemas are derived from the Pydantic models to ensure they stay in sync.
Any changes to the Pydantic models will automatically reflect in the API documentation.
"""

from typing import Any

from marshmallow import Schema, fields, validate
from pydantic import BaseModel

# Import Pydantic models for auto-generation (imported here to avoid circular imports later)
from backend.pro_players import Player
from backend.stats import StatsResponse, TeamStats

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
                # Use dump_default=None instead of allow_none=True for cleaner OpenAPI spec
                return fields.Nested(
                    nested_schema, required=False, dump_default=None, load_default=None, metadata=metadata
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


class ErrorSchema(Schema):
    """Base error response schema (RFC 7807-inspired)."""

    class Meta:
        """Schema metadata configuration."""

        ordered = True

    status = fields.Int(required=True, metadata={"description": "HTTP status code", "example": 400})
    code = fields.Str(
        required=True, metadata={"description": "Machine-readable error code", "example": "MISSING_TEAMS"}
    )
    message = fields.Str(
        required=True, metadata={"description": "Human-readable error message", "example": "No teams provided"}
    )
    details = fields.Dict(
        keys=fields.Str(),
        values=fields.Raw(),
        load_default=dict,
        metadata={"description": "Additional error context", "example": {"url": "/api/statistics"}},
    )


class TeamStatisticsQuerySchema(Schema):
    """Query parameters for team statistics endpoint."""

    team = fields.List(
        fields.Str(),
        required=False,
        validate=validate.Length(min=1, max=10),
        metadata={
            "description": (
                "Team names to analyze (1-10 teams). " "Can be specified multiple times: `?team=Alpha&team=Beta`"
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


class ProgressUpdateSchema(Schema):
    """Progress update schema for SSE streaming."""

    step = fields.Int(required=True, metadata={"description": "Current step number"})
    message = fields.Str(required=True, metadata={"description": "Progress message"})
    progress = fields.Float(required=True, metadata={"description": "Progress percentage (0-100)"})
    data = fields.Dict(keys=fields.Str(), values=fields.Raw(), metadata={"description": "Additional progress data"})


class TeamSchema(Schema):
    """Team information schema."""

    team_id = fields.Int(required=True, metadata={"description": "Unique team identifier"})
    name = fields.Str(required=True, metadata={"description": "Team name"})
    tag = fields.Str(allow_none=True, metadata={"description": "Team tag/abbreviation"})
    logo_url = fields.Str(allow_none=True, metadata={"description": "URL to team logo"})
    rating = fields.Float(allow_none=True, metadata={"description": "Team rating"})


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


class SyncResponseSchema(Schema):
    """Sync operation response schema."""

    synced_count = fields.Int(required=True, metadata={"description": "Number of records synced"})
    message = fields.Str(required=True, metadata={"description": "Operation result message"})


class StatisticsQuerySchema(Schema):
    """Query parameters for statistics computation endpoint."""

    team_id = fields.Int(required=True, metadata={"description": "Team ID to analyze"})
    num_matches = fields.Int(
        load_default=20,
        validate=validate.Range(min=1, max=100),
        metadata={"description": "Number of matches to analyze (default: 20, max: 100)"},
    )


class StatisticsBodySchema(Schema):
    """Request body for statistics computation endpoint."""

    team_id = fields.Int(required=True, metadata={"description": "Team ID to analyze"})
    num_matches = fields.Int(
        load_default=20,
        validate=validate.Range(min=1, max=100),
        metadata={"description": "Number of matches to analyze (default: 20, max: 100)"},
    )


class MatchStatsSchema(Schema):
    """Schema for individual match statistics."""

    match_id = fields.Int(required=True, metadata={"description": "Unique match identifier"})
    player_slot = fields.Int(required=True, metadata={"description": "Player slot number (0-127)"})
    radiant_win = fields.Bool(required=True, metadata={"description": "True if Radiant won"})
    game_mode = fields.Int(required=True, metadata={"description": "Game mode ID"})
    lobby_type = fields.Int(required=True, metadata={"description": "Lobby type ID"})
    hero_id = fields.Int(required=True, metadata={"description": "Hero ID played"})
    average_rank = fields.Int(allow_none=True, metadata={"description": "Average rank tier of the match"})


class PlayerResultSchema(Schema):
    """Schema for individual player result entry."""

    account_id = fields.Int(required=True, metadata={"description": "Player account ID"})
    match_count = fields.Int(metadata={"description": "Number of matches fetched for this player"})
    matches = fields.List(
        fields.Nested(MatchStatsSchema),
        metadata={"description": "List of match statistics for this player"},
    )
    error = fields.Str(metadata={"description": "Error message if player data fetch failed"})


class MatchesSummarySchema(Schema):
    """Schema for match collection summary statistics."""

    rating_matches = fields.Int(load_default=0, metadata={"description": "Number of rating matches (ranked games)"})
    tournament_matches = fields.Int(
        load_default=0, metadata={"description": "Number of tournament matches (competitive games)"}
    )
    other_matches = fields.Int(load_default=0, metadata={"description": "Number of other matches"})
    matches_median = fields.Float(allow_none=True, metadata={"description": "Median number of matches per player"})
    matches_avg = fields.Float(allow_none=True, metadata={"description": "Average number of matches per player"})
    win_percentage = fields.Float(allow_none=True, metadata={"description": "Team win percentage across all matches"})
    avg_rank = fields.Float(allow_none=True, metadata={"description": "Average player rank"})
    bad_rank_players = fields.Int(allow_none=True, metadata={"description": "Number of players with rank > 1000"})


class StatisticsResultSchema(Schema):
    """Complete statistics computation result schema.

    This is the final result structure returned by /api/results/<task_id>
    after the background task completes.
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


# Auto-generated schemas from Pydantic models
# These are generated at module import time to ensure they stay in sync with Pydantic models
# If you modify the Pydantic models (Player, TeamStats, StatsResponse), these schemas
# will automatically reflect those changes.

# Generate schemas from Pydantic models
PlayerSchema = pydantic_to_marshmallow(Player)
TeamStatsSchema = pydantic_to_marshmallow(TeamStats)
StatsResponseSchema = pydantic_to_marshmallow(StatsResponse)
