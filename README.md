# Fantasy Football Stats

A responsive web app (built for iPhone, works anywhere) that tracks NFL game
stats by player, computes fantasy points, and ranks players by season and by
week.

This is the first slice of a larger fantasy football app — start small with
player and game stat tracking, then build out from there.

## Features

- **Player list + search** — browse and search players by name, team, or
  position, sorted by fantasy production.
- **Per-game stat lines** — a full game log for each player (passing, rushing,
  receiving).
- **Season totals** — aggregated stats and fantasy points for the season.
- **Fantasy points** — PPR, Half-PPR, and Standard scoring.
- **Rankings** — fantasy point leaderboards for a whole season or a single
  week, filterable by position and scoring format.
- **Leagues** — create a league with any 2-16 teams, assign rosters from the
  full player pool, and run it: a round-robin schedule is generated
  automatically, with weekly head-to-head scoreboards and a live standings
  table (W/L/T, points for/against). Leagues are saved to disk.

## Data

Live NFL stats come from the [nflverse](https://github.com/nflverse/nflverse-data)
project's weekly player stats releases. The backend downloads and caches each
season's data on demand (cached under `.cache/`, refreshed every few hours).

Leagues you create are stored as JSON under `.data/leagues.json` so they
survive server restarts.

## Run

```bash
python src/main.py
```

Then open `http://localhost:8000/` — on an iPhone, use "Add to Home Screen" in
Safari for a full-screen app experience.

No third-party dependencies — the backend uses only the Python standard library.

### Configuration

- `PORT` — server port (default `8000`)
- `HOST` — bind address (default `0.0.0.0`)

## API

The frontend is served by a small JSON API:

- `GET /api/seasons` — available seasons
- `GET /api/players?season=&q=&position=` — player list / search
- `GET /api/player/<id>?season=` — player detail: season totals + game log
- `GET /api/rankings?season=&scope=season|week&week=&position=&scoring=` — rankings
- `GET /api/leagues` — list saved leagues
- `POST /api/leagues` — create a league (`{name, season, scoring, teams: [...]}`)
- `GET /api/leagues/<id>` — league detail: teams, rosters, schedule, standings
- `GET /api/leagues/<id>/scoreboard?week=` — weekly head-to-head matchups
- `POST /api/leagues/<id>/roster` — set a team's roster (`{team_id, player_ids}`)
- `DELETE /api/leagues/<id>` — delete a league

## Tests

```bash
python -m unittest discover tests
```

Tests cover CSV parsing, stat aggregation, fantasy scoring, search, rankings,
schedule generation, league scoring/standings, and the league store — all
without network access.
