from backend import create_app


def test_get_statistics_query_params(monkeypatch):
    # Mock compute_statistics for endpoint tests to avoid network calls
    from backend.stats import Player, StatsResponse, TeamStats

    def fake_compute(teams):
        return StatsResponse(
            teams=[
                TeamStats(team=team, team_id=idx + 1, players=[Player(name=f"{team}Player", id=idx + 1)])
                for idx, team in enumerate(teams)
            ]
        )

    monkeypatch.setattr("backend.dota_bet_analyzer.compute_statistics", fake_compute)

    app = create_app(test_config={})
    client = app.test_client()

    rv = client.get("/api/statistics?team=Alpha&team=Beta")
    # Verify HTTP status code is 200
    assert rv.status_code == 200, f"Expected 200, got {rv.status_code}"
    data = rv.get_json()
    assert "teams" in data
    assert isinstance(data["teams"], list)
    assert len(data["teams"]) == 2
    assert data["teams"][0]["team"] == "Alpha"


def test_get_statistics_numbered_params(monkeypatch):
    from backend.stats import Player, StatsResponse, TeamStats

    def fake_compute(teams):
        return StatsResponse(
            teams=[
                TeamStats(team=team, team_id=idx + 1, players=[Player(name=f"{team}Player", id=idx + 1)])
                for idx, team in enumerate(teams)
            ]
        )

    monkeypatch.setattr("backend.dota_bet_analyzer.compute_statistics", fake_compute)

    # Support team1=Alpha&team2=Beta style as well
    app = create_app(test_config={})
    client = app.test_client()

    rv = client.get("/api/statistics?team1=Alpha&team2=Beta")
    assert rv.status_code == 200
    data = rv.get_json()
    assert len(data["teams"]) == 2
    assert data["teams"][1]["team"] == "Beta"


def test_get_trims_and_filters_teams(monkeypatch):
    # Whitespace should be trimmed
    from backend.stats import Player, StatsResponse, TeamStats

    def fake_compute(teams):
        return StatsResponse(
            teams=[
                TeamStats(team=t.strip(), team_id=i + 1, players=[Player(name=f"{t.strip()}Player", id=i + 1)])
                for i, t in enumerate(teams)
                if isinstance(t, str) and t.strip()
            ]
        )

    monkeypatch.setattr("backend.dota_bet_analyzer.compute_statistics", fake_compute)

    app = create_app(test_config={})
    client = app.test_client()

    rv = client.get("/api/statistics?team=%20%20A%20%20&team=B%20")
    assert rv.status_code == 200
    data = rv.get_json()
    assert len(data["teams"]) == 2
    assert data["teams"][0]["team"] == "A"
    assert data["teams"][1]["team"] == "B"


def test_too_many_teams_returns_422():
    app = create_app(test_config={})
    client = app.test_client()

    many = "&".join([f"team=T{i}" for i in range(12)])
    rv = client.get(f"/api/statistics?{many}")
    # flask-smorest returns 422 for schema validation errors
    assert rv.status_code == 422


def test_no_teams_returns_422():
    """Test that missing teams returns 422 with MISSING_TEAMS error code."""
    app = create_app(test_config={})
    client = app.test_client()

    rv = client.get("/api/statistics")
    assert rv.status_code == 422
    data = rv.get_json()
    assert data["code"] == "MISSING_TEAMS"
    assert "message" in data
    assert "details" in data


def test_response_shape_contains_expected_fields(monkeypatch):
    from backend.stats import Player, StatsResponse, TeamStats

    def fake_compute(teams):
        return StatsResponse(
            teams=[
                TeamStats(team=team, team_id=idx + 1, players=[Player(name=f"{team}Player", id=idx + 1)])
                for idx, team in enumerate(teams)
            ]
        )

    monkeypatch.setattr("backend.dota_bet_analyzer.compute_statistics", fake_compute)

    app = create_app(test_config={})
    client = app.test_client()

    rv = client.get("/api/statistics?team=Single")
    assert rv.status_code == 200
    data = rv.get_json()
    assert "teams" in data and isinstance(data["teams"], list) and len(data["teams"]) == 1

    team = data["teams"][0]
    # Expected model fields
    assert "team" in team and isinstance(team["team"], str)
    assert "team_id" in team and isinstance(team["team_id"], int)
    assert "players" in team and isinstance(team["players"], list)
    if team["players"]:
        p = team["players"][0]
        assert "name" in p and "id" in p


def test_compute_statistics_exception_returns_500(monkeypatch):
    """Test that unexpected exceptions in compute_statistics return 500 with proper error structure."""

    def fake_compute_raises(teams):
        raise RuntimeError("Database connection failed")

    monkeypatch.setattr("backend.dota_bet_analyzer.compute_statistics", fake_compute_raises)

    app = create_app(test_config={})
    client = app.test_client()

    rv = client.get("/api/statistics?team=TestTeam")
    assert rv.status_code == 500

    data = rv.get_json()
    # Verify error response structure
    assert "status" in data
    assert "code" in data
    assert "message" in data
    assert "details" in data
    assert data["status"] == 500
    assert data["code"] == "COMPUTATION_ERROR"
    assert "exception" in data["details"]


def test_compute_statistics_value_error_returns_400(monkeypatch):
    """Test that ValueError in compute_statistics returns 400."""

    def fake_compute_raises(teams):
        raise ValueError("teams must be a list of strings")

    monkeypatch.setattr("backend.dota_bet_analyzer.compute_statistics", fake_compute_raises)

    app = create_app(test_config={})
    client = app.test_client()

    rv = client.get("/api/statistics?team=TestTeam")
    assert rv.status_code == 400

    data = rv.get_json()
    # Verify error response structure
    assert "status" in data
    assert "code" in data
    assert "message" in data
    assert data["status"] == 400
    assert data["code"] == "INVALID_REQUEST"
