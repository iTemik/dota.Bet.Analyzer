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

    rv = client.get("/statistics?team=Alpha&team=Beta")
    assert rv.status_code == 200
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

    rv = client.get("/statistics?team1=Alpha&team2=Beta")
    assert rv.status_code == 200
    data = rv.get_json()
    assert len(data["teams"]) == 2
    assert data["teams"][1]["team"] == "Beta"


def test_post_statistics_json_body(monkeypatch):
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

    rv = client.post("/statistics", json={"teams": ["X", "Y", "Z"]})
    assert rv.status_code == 200
    data = rv.get_json()
    assert len(data["teams"]) == 3
    assert data["teams"][2]["team"] == "Z"


def test_post_trims_and_filters_teams(monkeypatch):
    # Mixed types and whitespace should be filtered/trimmed
    from backend.stats import Player, StatsResponse, TeamStats

    def fake_compute(teams):
        return StatsResponse(
            teams=[
                TeamStats(team=t.strip(), team_id=i + 1, players=[Player(name=f"{t.strip()}Player", id=i + 1)])
                for i, t in enumerate(teams)
                if isinstance(t, str) and t.strip()
            ]
        )

    monkeypatch.setattr("backend.stats.compute_statistics", fake_compute)

    app = create_app(test_config={})
    client = app.test_client()

    rv = client.post("/statistics", json={"teams": ["  A  ", 123, None, "B "]})
    assert rv.status_code == 200
    data = rv.get_json()
    assert len(data["teams"]) == 2
    assert data["teams"][0]["team"] == "A"
    assert data["teams"][1]["team"] == "B"


def test_too_many_teams_returns_400():
    app = create_app(test_config={})
    client = app.test_client()

    many = [f"T{i}" for i in range(12)]
    rv = client.post("/statistics", json={"teams": many})
    assert rv.status_code == 400


def test_no_teams_returns_400():
    app = create_app(test_config={})
    client = app.test_client()

    rv = client.get("/statistics")
    assert rv.status_code == 400
    rv = client.post("/statistics", json={})
    assert rv.status_code == 400


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

    rv = client.post("/statistics", json={"teams": ["Single"]})
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
