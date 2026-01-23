"""Marshmallow schemas for API request/response validation and OpenAPI documentation."""

from marshmallow import Schema, fields, validate


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


class TeamSearchErrorSchema(ErrorSchema):
    """Error response schema for team search endpoint."""

    pass


class PlayerStatisticsErrorSchema(ErrorSchema):
    """Error response schema for player statistics endpoint."""

    pass


class TaskResultsErrorSchema(ErrorSchema):
    """Error response schema for task results endpoint."""

    pass


class SyncErrorSchema(ErrorSchema):
    """Error response schema for sync endpoints."""

    pass


class StatisticsErrorSchema(ErrorSchema):
    """Error response schema for statistics endpoint."""

    pass


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


class MatchSummarySchema(Schema):
    """Match summary information schema."""

    match_id = fields.Int(required=True, metadata={"description": "Unique match identifier"})
    start_time = fields.Int(required=True, metadata={"description": "Match start timestamp"})
    duration = fields.Int(required=True, metadata={"description": "Match duration in seconds"})
    radiant_win = fields.Bool(required=True, metadata={"description": "True if Radiant won"})
    radiant_score = fields.Int(required=True, metadata={"description": "Radiant team kills"})
    dire_score = fields.Int(required=True, metadata={"description": "Dire team kills"})


class PlayerMatchStatsSchema(Schema):
    """Player statistics for a match."""

    account_id = fields.Int(required=True, metadata={"description": "Player account ID"})
    hero_id = fields.Int(required=True, metadata={"description": "Hero ID played"})
    kills = fields.Int(required=True, metadata={"description": "Player kills"})
    deaths = fields.Int(required=True, metadata={"description": "Player deaths"})
    assists = fields.Int(required=True, metadata={"description": "Player assists"})
    gold_per_min = fields.Int(required=True, metadata={"description": "Gold per minute"})
    xp_per_min = fields.Int(required=True, metadata={"description": "Experience per minute"})


class StatisticsResultSchema(Schema):
    """Complete statistics computation result schema."""

    team_id = fields.Int(required=True, metadata={"description": "Team ID analyzed"})
    matches = fields.List(fields.Nested(MatchSummarySchema), metadata={"description": "List of matches analyzed"})
    player_stats = fields.Dict(
        keys=fields.Str(),
        values=fields.Nested(PlayerMatchStatsSchema),
        metadata={"description": "Player statistics by account_id"},
    )
    team_stats = fields.Dict(keys=fields.Str(), values=fields.Raw(), metadata={"description": "Team-level statistics"})
