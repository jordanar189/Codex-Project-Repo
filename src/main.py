"""Fantasy Football Stats - backend server.

Serves a responsive web app that tracks NFL game stats by player, using live
data from the nflverse project (https://github.com/nflverse/nflverse-data).

Run:
    python src/main.py
Then open http://localhost:8000/

The data layer (parsing / aggregation / fantasy scoring / ranking) is written
as pure functions so it can be unit tested without network access.
"""

from __future__ import annotations

import csv
import io
import json
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache", "nfl"
)

# nflverse weekly player stats, one CSV per season.
DATA_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "player_stats/stats_player_week_{season}.csv"
)

# How long a cached season file is considered fresh (seconds). The in-season
# data updates a few times a week, so a few hours keeps things reasonably live
# without re-downloading on every request.
CACHE_TTL = 6 * 60 * 60

# Counting stats we surface per game and aggregate into season totals.
STAT_FIELDS = [
    "completions",
    "attempts",
    "passing_yards",
    "passing_tds",
    "passing_interceptions",
    "carries",
    "rushing_yards",
    "rushing_tds",
    "receptions",
    "targets",
    "receiving_yards",
    "receiving_tds",
    "sack_fumbles_lost",
    "rushing_fumbles_lost",
    "receiving_fumbles_lost",
    "passing_2pt_conversions",
    "rushing_2pt_conversions",
    "receiving_2pt_conversions",
    "special_teams_tds",
    "fg_made",
    "fg_att",
    "pat_made",
    "pat_att",
    "fantasy_points",
    "fantasy_points_ppr",
]


# --------------------------------------------------------------------------
# Pure data layer (no network) - unit tested in tests/test_main.py
# --------------------------------------------------------------------------

def _num(value):
    """Parse a CSV cell into a number, treating blanks/NA as 0."""
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value) if float(value).is_integer() else round(value, 2)
    value = value.strip()
    if value == "" or value.upper() in ("NA", "NAN", "NULL"):
        return 0
    try:
        f = float(value)
    except ValueError:
        return 0
    return int(f) if f.is_integer() else round(f, 2)


def half_ppr(game):
    """Half-PPR fantasy points: standard scoring plus 0.5 per reception."""
    return round(_num(game.get("fantasy_points")) + 0.5 * _num(game.get("receptions")), 2)


def parse_player_stats(csv_text):
    """Parse an nflverse weekly stats CSV into a dict keyed by player id.

    Each value is a player dict with metadata and a ``games`` list. Only
    regular-season ("REG") rows are kept. Pure function - no network.
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    players = {}
    for row in reader:
        if (row.get("season_type") or "").upper() != "REG":
            continue
        pid = row.get("player_id")
        if not pid:
            continue
        player = players.get(pid)
        if player is None:
            player = {
                "id": pid,
                "name": row.get("player_display_name") or row.get("player_name") or pid,
                "position": row.get("position") or "",
                "position_group": row.get("position_group") or "",
                "headshot_url": row.get("headshot_url") or "",
                "team": row.get("team") or "",
                "games": [],
            }
            players[pid] = player
        # Keep the most recent team we see for the player.
        if row.get("team"):
            player["team"] = row["team"]
        game = {
            "season": _num(row.get("season")),
            "week": _num(row.get("week")),
            "team": row.get("team") or "",
            "opponent": row.get("opponent_team") or "",
        }
        for field in STAT_FIELDS:
            game[field] = _num(row.get(field))
        game["fantasy_points_half_ppr"] = half_ppr(game)
        player["games"].append(game)

    for player in players.values():
        player["games"].sort(key=lambda g: g["week"])
    return players


def season_totals(games):
    """Aggregate a list of game stat lines into season totals."""
    totals = {field: 0 for field in STAT_FIELDS}
    totals["fantasy_points_half_ppr"] = 0
    totals["games_played"] = len(games)
    for game in games:
        for field in STAT_FIELDS:
            totals[field] += game.get(field, 0)
        totals["fantasy_points_half_ppr"] += game.get("fantasy_points_half_ppr", 0)
    for key, value in totals.items():
        if isinstance(value, float):
            totals[key] = round(value, 2)
    return totals


SCORING_FIELD = {
    "standard": "fantasy_points",
    "ppr": "fantasy_points_ppr",
    "half": "fantasy_points_half_ppr",
}


def _scoring_field(scoring):
    return SCORING_FIELD.get((scoring or "ppr").lower(), "fantasy_points_ppr")


def player_summary(player, scoring="ppr"):
    """Lightweight per-player summary used in list / search responses."""
    totals = season_totals(player["games"])
    field = _scoring_field(scoring)
    points = totals[field]
    games = totals["games_played"] or 1
    return {
        "id": player["id"],
        "name": player["name"],
        "position": player["position"],
        "team": player["team"],
        "headshot_url": player["headshot_url"],
        "games_played": totals["games_played"],
        "fantasy_points": totals["fantasy_points"],
        "fantasy_points_ppr": totals["fantasy_points_ppr"],
        "fantasy_points_half_ppr": totals["fantasy_points_half_ppr"],
        "points": points,
        "points_per_game": round(points / games, 2),
    }


def search_players(players, query="", position="", scoring="ppr", limit=100):
    """Filter players by name/team/position, sorted by fantasy points."""
    query = (query or "").strip().lower()
    position = (position or "").strip().upper()
    results = []
    for player in players.values():
        if position and position not in ("ALL", "") and player["position"].upper() != position:
            continue
        if query:
            haystack = f"{player['name']} {player['team']} {player['position']}".lower()
            if query not in haystack:
                continue
        results.append(player_summary(player, scoring))
    results.sort(key=lambda p: p["points"], reverse=True)
    if limit:
        results = results[:limit]
    return results


def rank_players(players, scope="season", week=None, position="ALL", scoring="ppr", limit=100):
    """Rank players by fantasy points for a whole season or a single week."""
    field = _scoring_field(scoring)
    position = (position or "ALL").strip().upper()
    rows = []
    for player in players.values():
        if position not in ("ALL", "") and player["position"].upper() != position:
            continue
        if scope == "week":
            games = [g for g in player["games"] if g["week"] == week]
            if not games:
                continue
            game = games[0]
            points = game[field]
            rows.append({
                "id": player["id"],
                "name": player["name"],
                "position": player["position"],
                "team": player["team"],
                "headshot_url": player["headshot_url"],
                "opponent": game["opponent"],
                "week": week,
                "points": points,
            })
        else:
            totals = season_totals(player["games"])
            gp = totals["games_played"]
            if not gp:
                continue
            points = totals[field]
            rows.append({
                "id": player["id"],
                "name": player["name"],
                "position": player["position"],
                "team": player["team"],
                "headshot_url": player["headshot_url"],
                "games_played": gp,
                "points": points,
                "points_per_game": round(points / gp, 2),
            })
    rows.sort(key=lambda r: r["points"], reverse=True)
    for i, row in enumerate(rows, start=1):
        row["rank"] = i
    if limit:
        rows = rows[:limit]
    return rows


def player_detail(player, scoring="ppr"):
    """Full player payload: metadata, season totals, and per-game stat lines."""
    return {
        "id": player["id"],
        "name": player["name"],
        "position": player["position"],
        "position_group": player["position_group"],
        "team": player["team"],
        "headshot_url": player["headshot_url"],
        "season_totals": season_totals(player["games"]),
        "games": player["games"],
        "scoring": (scoring or "ppr").lower(),
    }


# --------------------------------------------------------------------------
# Data store - fetches + caches nflverse CSVs (network)
# --------------------------------------------------------------------------

class NFLData:
    """Fetches nflverse weekly stats and caches parsed results per season."""

    def __init__(self, data_url=DATA_URL, cache_dir=CACHE_DIR, ttl=CACHE_TTL):
        self.data_url = data_url
        self.cache_dir = cache_dir
        self.ttl = ttl
        self._parsed = {}          # season -> parsed players dict
        self._seasons = None       # cached list of available seasons
        self._lock = threading.Lock()
        os.makedirs(self.cache_dir, exist_ok=True)

    def _cache_path(self, season):
        return os.path.join(self.cache_dir, f"stats_player_week_{season}.csv")

    def _fetch_csv(self, season):
        """Return CSV text for a season, using a fresh on-disk cache if present."""
        path = self._cache_path(season)
        if os.path.exists(path) and (time.time() - os.path.getmtime(path)) < self.ttl:
            with open(path, "r", encoding="utf-8") as fh:
                return fh.read()
        url = self.data_url.format(season=season)
        req = urllib.request.Request(url, headers={"User-Agent": "fantasy-football-app"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return text

    def players(self, season):
        """Return the parsed players dict for a season (cached in memory)."""
        with self._lock:
            if season not in self._parsed:
                self._parsed[season] = parse_player_stats(self._fetch_csv(season))
            return self._parsed[season]

    def available_seasons(self):
        """Probe nflverse for which season files exist (cached after first call)."""
        with self._lock:
            if self._seasons is not None:
                return self._seasons
            found = []
            for season in range(date.today().year, 2015, -1):
                # A cached file means the season is definitely available.
                if os.path.exists(self._cache_path(season)):
                    found.append(season)
                    continue
                url = self.data_url.format(season=season)
                req = urllib.request.Request(
                    url, method="HEAD", headers={"User-Agent": "fantasy-football-app"}
                )
                try:
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        if resp.status == 200:
                            found.append(season)
                except Exception:
                    continue
            self._seasons = found
            return found

    def default_season(self):
        seasons = self.available_seasons()
        return seasons[0] if seasons else date.today().year


# --------------------------------------------------------------------------
# HTTP server
# --------------------------------------------------------------------------

DATA = NFLData()

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "FantasyFootball/1.0"

    def log_message(self, fmt, *args):  # quieter logging
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def _send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status, message):
        self._send_json({"error": message}, status=status)

    def _season_param(self, params):
        raw = params.get("season", [None])[0]
        if raw:
            try:
                return int(raw)
            except ValueError:
                pass
        return DATA.default_season()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        try:
            if path.startswith("/api/"):
                self._handle_api(path, params)
            else:
                self._handle_static(path)
        except urllib.error.HTTPError as exc:
            self._send_error_json(502, f"upstream data error ({exc.code})")
        except urllib.error.URLError as exc:
            self._send_error_json(502, f"could not reach data source: {exc.reason}")
        except BrokenPipeError:
            pass
        except Exception as exc:  # pragma: no cover - defensive
            self._send_error_json(500, f"server error: {exc}")

    # -- API routes --------------------------------------------------------

    def _handle_api(self, path, params):
        if path == "/api/seasons":
            seasons = DATA.available_seasons()
            self._send_json({"seasons": seasons, "default": DATA.default_season()})
            return

        if path == "/api/players":
            season = self._season_param(params)
            players = DATA.players(season)
            results = search_players(
                players,
                query=params.get("q", [""])[0],
                position=params.get("position", ["ALL"])[0],
                scoring=params.get("scoring", ["ppr"])[0],
                limit=int(params.get("limit", ["150"])[0]),
            )
            self._send_json({"season": season, "count": len(results), "players": results})
            return

        if path == "/api/rankings":
            season = self._season_param(params)
            players = DATA.players(season)
            scope = params.get("scope", ["season"])[0]
            week_raw = params.get("week", [None])[0]
            week = int(week_raw) if week_raw else None
            if scope == "week" and week is None:
                self._send_error_json(400, "week is required when scope=week")
                return
            results = rank_players(
                players,
                scope=scope,
                week=week,
                position=params.get("position", ["ALL"])[0],
                scoring=params.get("scoring", ["ppr"])[0],
                limit=int(params.get("limit", ["100"])[0]),
            )
            self._send_json({
                "season": season,
                "scope": scope,
                "week": week,
                "scoring": params.get("scoring", ["ppr"])[0],
                "count": len(results),
                "rankings": results,
            })
            return

        if path.startswith("/api/player/"):
            pid = path[len("/api/player/"):]
            season = self._season_param(params)
            players = DATA.players(season)
            player = players.get(pid)
            if player is None:
                self._send_error_json(404, "player not found")
                return
            payload = player_detail(player, scoring=params.get("scoring", ["ppr"])[0])
            payload["season"] = season
            self._send_json(payload)
            return

        self._send_error_json(404, "unknown endpoint")

    # -- Static files ------------------------------------------------------

    def _handle_static(self, path):
        if path == "/":
            path = "/index.html"
        rel = os.path.normpath(path.lstrip("/"))
        full = os.path.join(WEB_DIR, rel)
        if not full.startswith(WEB_DIR) or not os.path.isfile(full):
            self.send_error(404, "Not found")
            return
        ext = os.path.splitext(full)[1]
        ctype = CONTENT_TYPES.get(ext, "application/octet-stream")
        with open(full, "rb") as fh:
            body = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Fantasy Football Stats running at http://localhost:{PORT}/")
    print("Data: nflverse weekly player stats. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
