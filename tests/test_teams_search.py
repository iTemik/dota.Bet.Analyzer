class TestTeamsSearch:
    """Test the /api/teams/search endpoint"""

    def _insert_teams(self, app, teams):
        """Helper method to insert teams into the test database.

        Args:
            app: Flask app instance
            teams: List of tuples containing (team_id, rating, name, tag, logo_url, last_match_time)
        """
        with app.app_context():
            from backend.pro_players import get_d2ba_db

            db = get_d2ba_db()
            cursor = db.cursor()

            for team in teams:
                sql = (
                    "INSERT INTO teams "
                    "(team_id, rating, name, tag, logo_url, last_match_time) "
                    "VALUES (?, ?, ?, ?, ?, ?)"
                )
                cursor.execute(sql, team)
            db.commit()

    def test_search_teams_missing_query(self, client):
        """Test search without query parameter returns 422"""
        response = client.get("/api/teams/search")
        assert response.status_code == 422
        data = response.get_json()
        # Validation errors now follow ErrorSchema format
        assert data["status"] == 422
        assert data["code"] == "VALIDATION_ERROR"
        assert "details" in data
        assert "errors" in data["details"]

    def test_search_teams_too_short_query(self, client):
        """Test search with query less than 2 characters returns 422"""
        response = client.get("/api/teams/search?q=L")
        assert response.status_code == 422
        data = response.get_json()
        # Validation errors now follow ErrorSchema format
        assert data["status"] == 422
        assert data["code"] == "VALIDATION_ERROR"
        assert "details" in data
        assert "errors" in data["details"]

    def test_search_teams_empty_query(self, client):
        """Test search with empty query returns 422"""
        response = client.get("/api/teams/search?q=")
        assert response.status_code == 422

    def test_search_teams_whitespace_only(self, client, app):
        """Test search with whitespace-only query (passes validation, returns no results)"""
        # Insert a team to ensure empty result is from query, not empty DB
        test_teams = [(1, 1500.0, "Team Test", "TT", "https://example.com/tt.png", 1609459200)]
        self._insert_teams(app, test_teams)

        response = client.get("/api/teams/search?q=%20%20")
        # Whitespace passes min length validation (2 chars)
        assert response.status_code == 200
        data = response.get_json()
        # But returns no results (no team names match whitespace)
        assert len(data) == 0

    def test_search_teams_successful_search(self, client, app):
        """Test successful team search with valid query"""
        # Insert sample teams into the test database
        test_teams = [
            (1, 1500.0, "Team Liquid", "Liquid", "https://example.com/liquid.png", 1609459200),
            (2, 1600.0, "Team Secret", "Secret", "https://example.com/secret.png", 1609545600),
            (3, 1400.0, "Evil Geniuses", "EG", "https://example.com/eg.png", 1609632000),
            (4, 1550.0, "OG", "OG", "https://example.com/og.png", 1609718400),
            (5, 1650.0, "Team Spirit", "Spirit", "https://example.com/spirit.png", 1609804800),
        ]
        self._insert_teams(app, test_teams)

        # Test search for "Team"
        response = client.get("/api/teams/search?q=Team")
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        assert len(data) > 0

        # Verify that results contain teams with "Team" in their name
        team_names = [team["name"] for team in data]
        assert "Team Liquid" in team_names
        assert "Team Secret" in team_names
        assert "Team Spirit" in team_names

    def test_search_teams_case_insensitive(self, client, app):
        """Test that search is case-insensitive"""
        test_teams = [(100, 1500.0, "Team Liquid", "Liquid", "https://example.com/liquid.png", 1609459200)]
        self._insert_teams(app, test_teams)

        # Test with lowercase query
        response = client.get("/api/teams/search?q=liquid")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) > 0
        assert data[0]["name"] == "Team Liquid"

    def test_search_teams_by_tag(self, client, app):
        """Test searching teams by their tag"""
        test_teams = [(200, 1400.0, "Evil Geniuses", "EG", "https://example.com/eg.png", 1609459200)]
        self._insert_teams(app, test_teams)

        # Search by tag
        response = client.get("/api/teams/search?q=EG")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) > 0
        assert data[0]["tag"] == "EG"
        assert data[0]["name"] == "Evil Geniuses"

    def test_search_teams_prioritization(self, client, app):
        """Test that teams starting with query are prioritized"""
        test_teams = [
            (300, 1500.0, "Alliance", "Alliance", "https://example.com/alliance.png", 1609459200),
            (301, 1500.0, "Team Alliance", "TA", "https://example.com/ta.png", 1609545600),
            (302, 1500.0, "Super Alliance", "SA", "https://example.com/sa.png", 1609632000),
        ]
        self._insert_teams(app, test_teams)

        # Search for "Alliance"
        response = client.get("/api/teams/search?q=Alliance")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) >= 2

        # "Alliance" should come before "Team Alliance" or "Super Alliance"
        # because it starts with the query
        assert data[0]["name"] == "Alliance"

    def test_search_teams_limit_parameter(self, client, app):
        """Test that limit parameter works correctly"""
        # Insert multiple test teams
        test_teams = [
            (
                400 + i,
                1500.0,
                f"Team {i+1:02d}",
                f"T{i+1:02d}",
                f"https://example.com/t{i+1:02d}.png",
                1609459200 + i * 86400,
            )
            for i in range(15)
        ]
        self._insert_teams(app, test_teams)

        # Test with limit=5
        response = client.get("/api/teams/search?q=Team&limit=5")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) == 5

        # Test with limit=10
        response = client.get("/api/teams/search?q=Team&limit=10")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) == 10

    def test_search_teams_no_results(self, client, app):
        """Test search with query that matches no teams"""
        test_teams = [(500, 1500.0, "Team Liquid", "Liquid", "https://example.com/liquid.png", 1609459200)]
        self._insert_teams(app, test_teams)

        # Search for something that doesn't exist
        response = client.get("/api/teams/search?q=NonExistentTeam")
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_search_teams_limit_non_numeric(self, client, app):
        """Test limit parameter with non-numeric value"""
        test_teams = [(600, 1500.0, "Team Test", "TT", "https://example.com/tt.png", 1609459200)]
        self._insert_teams(app, test_teams)

        # Test with non-numeric limit
        response = client.get("/api/teams/search?q=Team&limit=abc")
        assert response.status_code == 422
        data = response.get_json()
        # Validation errors now follow ErrorSchema format
        assert data["status"] == 422
        assert data["code"] == "VALIDATION_ERROR"
        assert "details" in data
        assert "errors" in data["details"]

    def test_search_teams_limit_negative(self, client, app):
        """Test limit parameter with negative value"""
        test_teams = [(700, 1500.0, "Team Test", "TT", "https://example.com/tt.png", 1609459200)]
        self._insert_teams(app, test_teams)

        # Test with negative limit
        response = client.get("/api/teams/search?q=Team&limit=-1")
        assert response.status_code == 422
        data = response.get_json()
        # Validation errors now follow ErrorSchema format
        assert data["status"] == 422
        assert data["code"] == "VALIDATION_ERROR"
        assert "details" in data
        assert "errors" in data["details"]

    def test_search_teams_limit_zero(self, client, app):
        """Test limit parameter with zero value"""
        test_teams = [(800, 1500.0, "Team Test", "TT", "https://example.com/tt.png", 1609459200)]
        self._insert_teams(app, test_teams)

        # Test with zero limit
        response = client.get("/api/teams/search?q=Team&limit=0")
        assert response.status_code == 422
        data = response.get_json()
        # Validation errors now follow ErrorSchema format
        assert data["status"] == 422
        assert data["code"] == "VALIDATION_ERROR"
        assert "details" in data
        assert "errors" in data["details"]

    def test_search_teams_limit_exceeds_max(self, client, app):
        """Test that limit exceeding max (50) is rejected with 422"""
        # Insert more than 50 teams
        test_teams = [
            (
                900 + i,
                1500.0,
                f"Team {i+1:03d}",
                f"T{i+1:03d}",
                f"https://example.com/t{i+1:03d}.png",
                1609459200 + i * 86400,
            )
            for i in range(60)
        ]
        self._insert_teams(app, test_teams)

        # Test with limit=100 (exceeds max, should return 422)
        response = client.get("/api/teams/search?q=Team&limit=100")
        assert response.status_code == 422
        data = response.get_json()
        # Validation errors now follow ErrorSchema format
        assert data["status"] == 422
        assert data["code"] == "VALIDATION_ERROR"
        assert "details" in data
        assert "errors" in data["details"]

    def test_search_teams_last_match_time_secondary_sort(self, client, app):
        """Test that within the same relevance tier teams are ordered by last_match_time descending"""
        # All three teams' names start with "Team" (same tier 0).
        # They have distinct last_match_time values so the secondary sort is observable.
        test_teams = [
            (1100, 1500.0, "Team Alpha", "TA", "https://example.com/ta.png", 1609459200),  # oldest
            (1101, 1500.0, "Team Beta", "TB", "https://example.com/tb.png", 1609718400),   # newest
            (1102, 1500.0, "Team Gamma", "TG", "https://example.com/tg.png", 1609545600),  # middle
        ]
        self._insert_teams(app, test_teams)

        response = client.get("/api/teams/search?q=Team")
        assert response.status_code == 200
        data = response.get_json()

        # Filter to only the teams we just inserted (other tests may have inserted "Team" teams)
        inserted_names = {"Team Alpha", "Team Beta", "Team Gamma"}
        our_teams = [t for t in data if t["name"] in inserted_names]
        assert len(our_teams) == 3

        # Within the same relevance tier the backend must order by last_match_time DESC
        assert our_teams[0]["name"] == "Team Beta"   # newest: 1609718400
        assert our_teams[1]["name"] == "Team Gamma"  # middle: 1609545600
        assert our_teams[2]["name"] == "Team Alpha"  # oldest: 1609459200

    def test_search_teams_returns_last_match_time(self, client, app):
        """Test that search results include last_match_time field"""
        test_teams = [(1000, 1500.0, "Team Test", "TT", "https://example.com/tt.png", 1609459200)]
        self._insert_teams(app, test_teams)

        response = client.get("/api/teams/search?q=Team")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) > 0
        team = data[0]

        # Verify all expected fields are present
        assert "team_id" in team
        assert "name" in team
        assert "tag" in team
        assert "logo_url" in team
        assert "rating" in team
        assert "last_match_time" in team
        assert team["last_match_time"] == 1609459200
