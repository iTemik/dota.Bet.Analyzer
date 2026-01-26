"""Tests to ensure Pydantic models and Marshmallow schemas stay synchronized."""

from typing import Any

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
                error=None,
            )
        ]
    )

    # Convert to dict (simulates endpoint return)
    dumped = sample_response.model_dump()

    # Verify Marshmallow can load it (validates schema compatibility)
    schema = StatsResponseSchema()
    loaded = schema.load(dumped)
    assert isinstance(loaded, dict)

    # Should be able to round-trip without errors
    assert loaded is not None
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
                "error",
            },
        ),
        ("Player", {"name", "id"}),
        ("ApiError", {"status", "code", "message", "details"}),
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

    # Import or generate Marshmallow schema
    schemas_module = importlib.import_module("backend.schemas")
    try:
        schema_class = getattr(schemas_module, f"{pydantic_class}Schema")
    except AttributeError:
        # Schema not exported, generate it
        from backend.schemas import pydantic_to_marshmallow

        schema_class = pydantic_to_marshmallow(pydantic_model)

    schema_fields = set(schema_class().fields.keys())

    # Verify alignment
    assert pydantic_fields == schema_fields, f"{pydantic_class}Schema not in sync with Pydantic model!"


def test_api_error_schema_generation():
    """Verify ApiError schema is generated with all fields including details."""
    from backend.schemas import pydantic_to_marshmallow
    from backend.stats import ApiError

    # Generate schema for ApiError
    ApiErrorSchema = pydantic_to_marshmallow(ApiError)
    schema = ApiErrorSchema()

    # Verify all fields are present
    assert "status" in schema.fields, "status field missing from ApiError schema"
    assert "code" in schema.fields, "code field missing from ApiError schema"
    assert "message" in schema.fields, "message field missing from ApiError schema"
    assert "details" in schema.fields, "details field missing from ApiError schema"

    # Verify field types
    from marshmallow import fields

    assert isinstance(schema.fields["status"], fields.Int)
    assert isinstance(schema.fields["code"], fields.Str)
    assert isinstance(schema.fields["message"], fields.Str)
    assert isinstance(schema.fields["details"], fields.Dict)

    # Verify all fields are optional (allow_none=True)
    assert schema.fields["status"].allow_none is True
    assert schema.fields["code"].allow_none is True
    assert schema.fields["message"].allow_none is True
    assert schema.fields["details"].allow_none is True


def test_api_error_schema_serialization() -> None:
    """Verify ApiError schema can serialize and deserialize correctly."""
    from backend.schemas import pydantic_to_marshmallow
    from backend.stats import ApiError

    ApiErrorSchema = pydantic_to_marshmallow(ApiError)
    schema = ApiErrorSchema()

    # Test with all fields populated
    error = ApiError(
        status=400,
        code="TEST_ERROR",
        message="Test error message",
        details={"url": "http://test.com", "status_code": 500},
    )
    dumped = error.model_dump()
    loaded: Any = schema.load(dumped)

    assert loaded["status"] == 400
    assert loaded["code"] == "TEST_ERROR"
    assert loaded["message"] == "Test error message"
    assert loaded["details"]["url"] == "http://test.com"
    assert loaded["details"]["status_code"] == 500

    # Test with None values
    error_none = ApiError(status=None, code=None, message=None, details=None)
    dumped_none = error_none.model_dump()
    loaded_none: Any = schema.load(dumped_none)

    assert loaded_none["status"] is None
    assert loaded_none["code"] is None
    assert loaded_none["message"] is None
    assert loaded_none["details"] is None


def test_team_stats_error_field_nested_schema() -> None:
    """Verify TeamStats error field contains properly nested ApiError schema."""
    from marshmallow import fields

    from backend.schemas import TeamStatsSchema

    schema = TeamStatsSchema()

    # Verify error field exists and is a Nested field
    assert "error" in schema.fields, "error field missing from TeamStats schema"
    error_field = schema.fields["error"]
    assert isinstance(error_field, fields.Nested), "error field should be Nested type"

    # Verify the nested schema is for ApiError
    # error_field.nested can be a schema class, instance, string (lazy reference), or dict
    nested_schema_ref = error_field.nested
    if isinstance(nested_schema_ref, str):
        # It's a lazy reference (string), skip detailed field checks
        # Just verify it's a non-empty string
        assert nested_schema_ref, "Nested schema reference should not be empty"
    elif isinstance(nested_schema_ref, dict):
        # It's a dict (shouldn't happen in normal cases but handle it)
        # Skip field checks for dict type
        pass
    elif isinstance(nested_schema_ref, type):
        # It's a class, instantiate it
        nested_schema = nested_schema_ref()
        assert hasattr(nested_schema, "fields"), "Schema instance should have fields attribute"
        assert "status" in nested_schema.fields
        assert "code" in nested_schema.fields
        assert "message" in nested_schema.fields
        assert "details" in nested_schema.fields
    else:
        # It's already an instance - verify it has fields attribute
        assert hasattr(nested_schema_ref, "fields"), "Schema instance should have fields attribute"
        assert "status" in nested_schema_ref.fields
        assert "code" in nested_schema_ref.fields
        assert "message" in nested_schema_ref.fields
        assert "details" in nested_schema_ref.fields

    # Verify it allows None (optional field)
    assert error_field.allow_none is True


def test_stats_response_with_api_error_serialization() -> None:
    """Verify StatsResponse correctly serializes TeamStats with ApiError."""
    from backend.pro_players import Player
    from backend.schemas import StatsResponseSchema
    from backend.stats import ApiError, StatsResponse, TeamStats

    # Create response with error
    sample_response = StatsResponse(
        teams=[
            TeamStats(
                team_id=1,
                team="Success Team",
                tag="ST",
                players=[Player(name="Player1", id=111)],
                error=None,
            ),
            TeamStats(
                team="Error Team",
                error=ApiError(
                    status=503,
                    code="NETWORK_ERROR",
                    message="Failed to fetch team data",
                    details={"url": "https://api.example.com/teams/999", "timeout": 5},
                ),
            ),
        ]
    )

    # Serialize using Pydantic
    dumped = sample_response.model_dump()

    # Deserialize using Marshmallow
    schema = StatsResponseSchema()
    loaded: Any = schema.load(dumped)

    # Verify successful team
    assert loaded["teams"][0]["team"] == "Success Team"
    assert loaded["teams"][0]["error"] is None

    # Verify error team - all ApiError fields should be present
    error_team = loaded["teams"][1]
    assert error_team["team"] == "Error Team"
    assert error_team["error"] is not None
    assert error_team["error"]["status"] == 503
    assert error_team["error"]["code"] == "NETWORK_ERROR"
    assert error_team["error"]["message"] == "Failed to fetch team data"
    assert error_team["error"]["details"]["url"] == "https://api.example.com/teams/999"
    assert error_team["error"]["details"]["timeout"] == 5


def test_openapi_spec_has_error_example():
    """Verify OpenAPI spec includes proper example for error field."""
    from apispec import APISpec
    from apispec.ext.marshmallow import MarshmallowPlugin

    from backend.schemas import StatsResponseSchema

    # Create APISpec like flask-smorest does
    spec = APISpec(title="Test API", version="1.0.0", openapi_version="3.0.0", plugins=[MarshmallowPlugin()])

    # Register schema
    spec.components.schema("StatsResponse", schema=StatsResponseSchema())

    # Get the generated spec
    spec_dict = spec.to_dict()

    # Verify ApiError schema is registered
    assert "ApiError" in spec_dict["components"]["schemas"]
    api_error_schema = spec_dict["components"]["schemas"]["ApiError"]
    assert "status" in api_error_schema["properties"]
    assert "code" in api_error_schema["properties"]
    assert "message" in api_error_schema["properties"]
    assert "details" in api_error_schema["properties"]

    # Verify TeamStats error field has proper structure
    assert "TeamStats" in spec_dict["components"]["schemas"]
    team_stats_schema = spec_dict["components"]["schemas"]["TeamStats"]
    error_field = team_stats_schema["properties"]["error"]

    # Verify error field has example metadata
    assert "example" in error_field
    assert error_field["example"]["status"] == 503
    assert error_field["example"]["code"] == "NETWORK_ERROR"
    assert error_field["example"]["message"] == "Failed to fetch data"
    assert "url" in error_field["example"]["details"]

    # Verify error field references ApiError schema (in anyOf for nullable support)
    assert "anyOf" in error_field
    refs = [item.get("$ref") for item in error_field["anyOf"] if "$ref" in item]
    assert "#/components/schemas/ApiError" in refs
