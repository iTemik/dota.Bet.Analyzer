# Pro Players Database

This module provides functionality to fetch and store Dota 2 pro player data from the OpenDota API.

## Database

The pro players data is stored in a separate SQLite database: `instance/d2ba.sqlite`

### Schema

**Table: `pro_players`**
- `account_id` (INTEGER, PRIMARY KEY) - Unique player account ID
- `steamid` (TEXT) - Steam ID
- `profileurl` (TEXT) - Steam profile URL
- `personaname` (TEXT) - Display name
- `name` (TEXT, INDEXED) - Player's real name
- `fantasy_role` (INTEGER) - Fantasy role (1-5)
- `team_id` (INTEGER, INDEXED) - Current team ID
- `team_name` (TEXT) - Team name
- `team_tag` (TEXT) - Team tag/abbreviation
- `is_pro` (BOOLEAN) - Pro player status

## Usage

### Initialize Database

```bash
python scripts/init_d2ba_db.py
```

This creates the `instance/d2ba.sqlite` database with the required schema.

### Fetch Pro Players

**Endpoint:** `GET /ProPlayers`

Fetches pro player data from OpenDota API and stores it in the database.

**Example:**
```bash
curl http://localhost:5000/ProPlayers
```

**Response:**
```json
{
  "status": "ok",
  "count": 500,
  "message": "Stored 500 pro players"
}
```

**Error Response:**
```json
{
  "error": "Failed to fetch pro players from OpenDota API"
}
```

## Implementation Details

- Data is fetched from: `https://api.opendota.com/api/proPlayers`
- Uses UPSERT logic: existing players are updated, new players are inserted
- Only stores the fields defined in the schema (other API fields are ignored)
- Separate database connection from main `opendota.sqlite` for better separation of concerns

## Testing

Run tests with:
```bash
pytest tests/test_init_d2ba_db.py tests/test_pro_players.py
```

**Test Coverage:**
- Database initialization (5 tests)
- API endpoint functionality (7 tests)
- Data storage and updates
- Error handling
