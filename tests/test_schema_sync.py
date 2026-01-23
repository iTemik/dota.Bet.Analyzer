"""Tests to ensure Pydantic models and Marshmallow schemas stay synchronized."""

import pytest


def test_stats_response_schema_fields_match_pydantic():
    """Verify StatsResponseSchema has same fields as StatsResponse Pydantic model."""
    from backend.schemas import StatsResponseSchema
    from backend.stats import StatsResponse

    pydantic_fields = set(StatsResponse.model_fields.keys())
    schema_fields = set(StatsResponseSchema().fields.keys())

    assert pydantic_fields == schema_fields, (
        f"StatsResponse schema mismatch!\n"
        f"Pydantic has: {pydantic_fields}\n"
        f"Marshmallow has: {schema_fields}\n"
        f"Missing in Marshmallow: {pydantic_fields - schema_fields}\n"
        f"Extra in Marshmallow: {schema_fields - pydantic_fields}"
    )


def test_team_stats_schema_fields_match_pydantic():
    """Verify TeamStatsSchema has same fields as TeamStats Pydantic model."""
    from backend.schemas import TeamStatsSchema
    from backend.stats import TeamStats

    pydantic_fields = set(TeamStats.model_fields.keys())
    schema_fields = set(TeamStatsSchema().fields.keys())

    assert pydantic_fields == schema_fields, (
        f"TeamStats schema mismatch!\n"
        f"Pydantic has: {pydantic_fields}\n"
        f"Marshmallow has: {schema_fields}\n"
        f"Missing in Marshmallow: {pydantic_fields - schema_fields}\n"
        f"Extra in Marshmallow: {schema_fields - pydantic_fields}"
    )


def test_player_schema_fields_match_pydantic():
    """Verify PlayerSchema has same fields as Player Pydantic model."""
    from backend.pro_players import Player
    from backend.schemas import PlayerSchema

    pydantic_fields = set(Player.model_fields.keys())
    schema_fields = set(PlayerSchema().fields.keys())

    assert pydantic_fields == schema_fields, (
        f"Player schema mismatch!\n"
        f"Pydantic has: {pydantic_fields}\n"
        f"Marshmallow has: {schema_fields}\n"
        f"Missing in Marshmallow: {pydantic_fields - schema_fields}\n"
        f"Extra in Marshmallow: {schema_fields - pydantic_fields}"
    )


def test_stats_response_serialization_compatibility():
    """Verify Marshmallow schema can serialize Pydantic model output."""
    from backend.pro_players import Player
    from backend.schemas import StatsResponseSchema
    from backend.stats import StatsResponse, TeamStats

    # Create sample Pydantic instance
    sample_response = StatsResponse(
        teams=[
            TeamStats(
                team_id=1,
                team="Test Team",
                tag="TT",
                rating=1500.0,
                delta=50.0,
                logo_url="http://example.com/logo.png",
                players=[Player(name="TestPlayer", id=12345)],
                other_players=[],
                task_id="task_123",
                error_code=None,
                message=None,
                details=None,
            )
        ]
    )

    # Convert to dict (simulates endpoint return)
    dumped = sample_response.model_dump()

    # Verify Marshmallow can load it (validates schema compatibility)
    schema = StatsResponseSchema()
    loaded = schema.load(dumped)

    # Should be able to round-trip without errors
    assert loaded["teams"][0]["team"] == "Test Team"
    assert loaded["teams"][0]["team_id"] == 1
    assert len(loaded["teams"][0]["players"]) == 1


def test_pydantic_to_marshmallow_utility():
    """Test the pydantic_to_marshmallow() auto-generation utility."""
    from backend.schemas import pydantic_to_marshmallow
    from backend.stats import Player

    # Auto-generate schema
    PlayerSchemaGenerated = pydantic_to_marshmallow(Player)

    # Verify it has the right fields
    schema_instance = PlayerSchemaGenerated()
    assert "name" in schema_instance.fields
    assert "id" in schema_instance.fields
    assert len(schema_instance.fields) == 2

    # Test it can serialize
    sample_data = {"name": "TestPlayer", "id": 123}
    loaded = schema_instance.load(sample_data)
    assert loaded == sample_data


@pytest.mark.parametrize(
    "pydantic_class,expected_fields",
    [
        ("StatsResponse", {"teams"}),
        (
            "TeamStats",
            {
                "team_id",
                "team",
                "tag",
                "rating",
                "delta",
                "logo_url",
                "players",
                "other_players",
                "task_id",
                "error_code",
                "message",
                "details",
            },
        ),
        ("Player", {"name", "id"}),
    ],
)
def test_all_pydantic_models_have_schemas(pydantic_class, expected_fields):
    """Verify all Pydantic models used in responses have corresponding schemas."""
    import importlib

    # Import Pydantic model
    if pydantic_class == "Player":
        module = importlib.import_module("backend.pro_players")
    else:
        module = importlib.import_module("backend.stats")

    pydantic_model = getattr(module, pydantic_class)
    pydantic_fields = set(pydantic_model.model_fields.keys())

    # Verify expected fields match
    assert pydantic_fields == expected_fields, f"{pydantic_class} fields changed - update tests!"

    # Import Marshmallow schema
    schemas_module = importlib.import_module("backend.schemas")
    schema_class = getattr(schemas_module, f"{pydantic_class}Schema")
    schema_fields = set(schema_class().fields.keys())

    # Verify alignment
    assert pydantic_fields == schema_fields, f"{pydantic_class}Schema not in sync with Pydantic model!"
