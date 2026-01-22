class TestTeamsSearch:
    """Test the /api/teams/search endpoint"""

    def _insert_teams(self, app, teams):
        """Helper method to insert teams into the test database.

        Args:
            app: Flask app instance
            teams: List of tuples containing (team_id, rating, name, tag, logo_url)
        """
        with app.app_context():
            from backend.pro_players import get_d2ba_db

            db = get_d2ba_db()
            cursor = db.cursor()

            for team in teams:
                cursor.execute(
                    "INSERT INTO teams (team_id, rating, name, tag, logo_url) VALUES (?, ?, ?, ?, ?)",
                    team,
                )
            db.commit()

    def test_search_teams_missing_query(self, client):
        """Test search without query parameter"""
        response = client.get("/api/teams/search")
        assert response.status_code == 400
        data = response.get_json()
        assert "message" in data
        assert "at least 2 characters" in data["message"].lower()

    def test_search_teams_too_short_query(self, client):
        """Test search with query less than 2 characters"""
        response = client.get("/api/teams/search?q=L")
        assert response.status_code == 400
        data = response.get_json()
        assert "at least 2 characters" in data["message"].lower()

    def test_search_teams_empty_query(self, client):
        """Test search with empty query"""
        response = client.get("/api/teams/search?q=")
        assert response.status_code == 400

    def test_search_teams_whitespace_only(self, client):
        """Test search with whitespace-only query"""
        response = client.get("/api/teams/search?q=%20%20")
        assert response.status_code == 400

    def test_search_teams_successful_search(self, client, app):
        """Test successful team search with valid query"""
        # Insert sample teams into the test database
        test_teams = [
            (1, 1500.0, "Team Liquid", "Liquid", "https://example.com/liquid.png"),
            (2, 1600.0, "Team Secret", "Secret", "https://example.com/secret.png"),
            (3, 1400.0, "Evil Geniuses", "EG", "https://example.com/eg.png"),
            (4, 1550.0, "OG", "OG", "https://example.com/og.png"),
            (5, 1650.0, "Team Spirit", "Spirit", "https://example.com/spirit.png"),
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
        test_teams = [(100, 1500.0, "Team Liquid", "Liquid", "https://example.com/liquid.png")]
        self._insert_teams(app, test_teams)

        # Test with lowercase query
        response = client.get("/api/teams/search?q=liquid")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) > 0
        assert data[0]["name"] == "Team Liquid"

    def test_search_teams_by_tag(self, client, app):
        """Test searching teams by their tag"""
        test_teams = [(200, 1400.0, "Evil Geniuses", "EG", "https://example.com/eg.png")]
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
            (300, 1500.0, "Alliance", "Alliance", "https://example.com/alliance.png"),
            (301, 1500.0, "Team Alliance", "TA", "https://example.com/ta.png"),
            (302, 1500.0, "Super Alliance", "SA", "https://example.com/sa.png"),
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
            (400 + i, 1500.0, f"Team {i+1:02d}", f"T{i+1:02d}", f"https://example.com/t{i+1:02d}.png")
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
        test_teams = [(500, 1500.0, "Team Liquid", "Liquid", "https://example.com/liquid.png")]
        self._insert_teams(app, test_teams)

        # Search for something that doesn't exist
        response = client.get("/api/teams/search?q=NonExistentTeam")
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        assert len(data) == 0
