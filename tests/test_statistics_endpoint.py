from backend import create_app


def fake_compute_with_kwargs(**kwargs):
    """Mock compute_statistics that handles both teams and team_ids."""
    from backend.stats import Player, StatsResponse, TeamStats

    teams = kwargs.get("teams") or []
    team_ids = kwargs.get("team_ids") or []

    # Combine both teams and team_ids
    all_items = []
    for team in teams:
        all_items.append((team, False))  # (item, is_id)
    for team_id in team_ids:
        all_items.append((team_id, True))  # (item, is_id)

    return StatsResponse(
        teams=[
            TeamStats(
                team=f"Team {item}" if is_id else item,
                team_id=item if is_id else idx + 1,
                players=[Player(name=f"Player{idx}", id=idx + 100)],
            )
            for idx, (item, is_id) in enumerate(all_items)
        ]
    )


def test_get_statistics_query_params(monkeypatch):
    # Mock compute_statistics for endpoint tests to avoid network calls
    monkeypatch.setattr("backend.dota_bet_analyzer.compute_statistics", fake_compute_with_kwargs)

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


def test_get_statistics_by_team_id(monkeypatch):
    """Test statistics endpoint with team_id parameters."""
    monkeypatch.setattr("backend.dota_bet_analyzer.compute_statistics", fake_compute_with_kwargs)

    app = create_app(test_config={})
    client = app.test_client()

    rv = client.get("/api/statistics?team_id=123&team_id=456")
    assert rv.status_code == 200
    data = rv.get_json()
    assert "teams" in data
    assert len(data["teams"]) == 2
    assert data["teams"][0]["team_id"] == 123
    assert data["teams"][1]["team_id"] == 456


def test_get_statistics_with_both_team_and_team_id(monkeypatch):
    """Test that both team and team_id can be provided together."""
    monkeypatch.setattr("backend.dota_bet_analyzer.compute_statistics", fake_compute_with_kwargs)

    app = create_app(test_config={})
    client = app.test_client()

    # Provide both team_id and team - both should be used
    rv = client.get("/api/statistics?team_id=123&team=Alpha")
    assert rv.status_code == 200
    data = rv.get_json()
    # Should have both teams
    assert len(data["teams"]) == 2
    assert any(t["team_id"] == 123 for t in data["teams"])
    assert any(t["team"] == "Alpha" for t in data["teams"])


def test_get_statistics_numbered_params(monkeypatch):
    monkeypatch.setattr("backend.dota_bet_analyzer.compute_statistics", fake_compute_with_kwargs)

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
    def fake_compute(teams=None, team_ids=None):
        from backend.stats import Player, StatsResponse, TeamStats

        items = team_ids if team_ids else (teams or [])
        return StatsResponse(
            teams=[
                TeamStats(
                    team=t.strip() if isinstance(t, str) else f"Team {t}",
                    team_id=i + 1,
                    players=[Player(name=f"Player{i}", id=i + 100)],
                )
                for i, t in enumerate(items)
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


def test_too_many_team_ids_returns_422():
    """Test that more than 10 team IDs returns 422."""
    app = create_app(test_config={})
    client = app.test_client()

    many = "&".join([f"team_id={i}" for i in range(11, 22)])
    rv = client.get(f"/api/statistics?{many}")
    assert rv.status_code == 422


def test_combined_teams_and_ids_exceeds_limit_returns_422():
    """Test that combined count of teams and team_ids exceeding 10 returns 422.

    This validates the edge case where neither parameter alone exceeds 10,
    but combined they do. For example: 6 teams + 6 team_ids = 12 total.
    """
    app = create_app(test_config={})
    client = app.test_client()

    # 6 teams + 6 team_ids = 12 total (exceeds limit of 10)
    teams_part = "&".join([f"team=T{i}" for i in range(6)])
    ids_part = "&".join([f"team_id={i}" for i in range(100, 106)])
    rv = client.get(f"/api/statistics?{teams_part}&{ids_part}")
    assert rv.status_code == 422
    data = rv.get_json()
    assert data["code"] == "TOO_MANY_TEAMS"


def test_combined_teams_and_ids_at_limit_returns_200(monkeypatch):
    """Test that combined count of exactly 10 teams and team_ids returns 200.

    This validates the edge case where combining teams and team_ids equals
    exactly 10, which should be allowed.
    """
    monkeypatch.setattr("backend.dota_bet_analyzer.compute_statistics", fake_compute_with_kwargs)

    app = create_app(test_config={})
    client = app.test_client()

    # 5 teams + 5 team_ids = 10 total (at limit, should succeed)
    teams_part = "&".join([f"team=T{i}" for i in range(5)])
    ids_part = "&".join([f"team_id={i}" for i in range(100, 105)])
    rv = client.get(f"/api/statistics?{teams_part}&{ids_part}")
    assert rv.status_code == 200
    data = rv.get_json()
    assert len(data["teams"]) == 10


def test_no_teams_returns_422():
    """Test that missing teams returns 422 with MISSING_TEAMS error code."""
    app = create_app(test_config={})
    client = app.test_client()

    rv = client.get("/api/statistics")
    assert rv.status_code == 422
    data = rv.get_json()
    assert data["code"] == "MISSING_TEAMS"
    assert "message" in data


def test_response_shape_contains_expected_fields(monkeypatch):
    monkeypatch.setattr("backend.dota_bet_analyzer.compute_statistics", fake_compute_with_kwargs)

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

    def fake_compute_raises(teams=None, team_ids=None):
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

    def fake_compute_raises(teams=None, team_ids=None):
        raise ValueError("Invalid parameter")

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
