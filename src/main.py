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
import secrets
import threading
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
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
# Fantasy league logic (pure, no network) - unit tested in tests/test_main.py
# --------------------------------------------------------------------------

def generate_schedule(team_ids):
    """Build a round-robin schedule from a list of team ids.

    Returns a list of ``{"week", "matchups", "byes"}`` dicts. With an odd
    number of teams, one team sits out (a bye) each week. Pure function.
    """
    teams = list(team_ids)
    bye_marker = None
    if len(teams) % 2 == 1:
        bye_marker = "__bye__"
        teams.append(bye_marker)
    count = len(teams)
    schedule = []
    rotation = teams[:]
    for week in range(1, count):  # count-1 rounds covers every pairing once
        matchups, byes = [], []
        for i in range(count // 2):
            a, b = rotation[i], rotation[count - 1 - i]
            if a == bye_marker:
                byes.append(b)
            elif b == bye_marker:
                byes.append(a)
            else:
                matchups.append([a, b])
        schedule.append({"week": week, "matchups": matchups, "byes": byes})
        # Rotate all but the first entry clockwise.
        rotation = [rotation[0], rotation[-1]] + rotation[1:-1]
    return schedule


def team_week_score(players, roster, week, scoring="ppr"):
    """Total fantasy points a roster scored in one week, plus a per-player
    breakdown. ``players`` is a parsed players dict. Pure function."""
    field = _scoring_field(scoring)
    total = 0.0
    breakdown = []
    for pid in roster:
        player = players.get(pid)
        games = (
            [g for g in player["games"] if g["week"] == week] if player else []
        )
        points = games[0][field] if games else 0
        total += points
        breakdown.append({
            "id": pid,
            "name": player["name"] if player else pid,
            "position": player["position"] if player else "",
            "team": player["team"] if player else "",
            "headshot_url": player["headshot_url"] if player else "",
            "points": points,
            "played": bool(games),
        })
    breakdown.sort(key=lambda p: p["points"], reverse=True)
    return round(total, 2), breakdown


def _team_lookup(league):
    return {team["id"]: team for team in league["teams"]}


def league_scoreboard(league, players, week):
    """Head-to-head matchups for one week with scores and roster breakdowns."""
    teams = _team_lookup(league)
    scoring = league.get("scoring", "ppr")
    week_plan = next((w for w in league["schedule"] if w["week"] == week), None)
    matchups = []
    byes = []
    if week_plan:
        for home_id, away_id in week_plan["matchups"]:
            home_pts, home_roster = team_week_score(
                players, teams[home_id]["roster"], week, scoring)
            away_pts, away_roster = team_week_score(
                players, teams[away_id]["roster"], week, scoring)
            played = any(p["played"] for p in home_roster + away_roster)
            matchups.append({
                "home": {"team_id": home_id, "name": teams[home_id]["name"],
                         "points": home_pts, "roster": home_roster},
                "away": {"team_id": away_id, "name": teams[away_id]["name"],
                         "points": away_pts, "roster": away_roster},
                "played": played,
            })
        byes = [{"team_id": tid, "name": teams[tid]["name"]}
                for tid in week_plan["byes"]]
    return {"week": week, "matchups": matchups, "byes": byes}


def league_standings(league, players):
    """Win/loss records and points for/against, sorted best-first.

    A matchup only counts once at least one rostered player has a game that
    week, so unplayed weeks don't drag every team to 0-0.
    """
    teams = _team_lookup(league)
    scoring = league.get("scoring", "ppr")
    table = {
        tid: {"team_id": tid, "name": team["name"], "wins": 0, "losses": 0,
              "ties": 0, "points_for": 0.0, "points_against": 0.0}
        for tid, team in teams.items()
    }
    for week_plan in league["schedule"]:
        week = week_plan["week"]
        for home_id, away_id in week_plan["matchups"]:
            home_pts, home_roster = team_week_score(
                players, teams[home_id]["roster"], week, scoring)
            away_pts, away_roster = team_week_score(
                players, teams[away_id]["roster"], week, scoring)
            if not any(p["played"] for p in home_roster + away_roster):
                continue
            home, away = table[home_id], table[away_id]
            home["points_for"] += home_pts
            home["points_against"] += away_pts
            away["points_for"] += away_pts
            away["points_against"] += home_pts
            if home_pts > away_pts:
                home["wins"] += 1
                away["losses"] += 1
            elif away_pts > home_pts:
                away["wins"] += 1
                home["losses"] += 1
            else:
                home["ties"] += 1
                away["ties"] += 1
    rows = list(table.values())
    for row in rows:
        row["points_for"] = round(row["points_for"], 2)
        row["points_against"] = round(row["points_against"], 2)
        row["games"] = row["wins"] + row["losses"] + row["ties"]
    rows.sort(key=lambda r: (r["wins"], r["points_for"]), reverse=True)
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows


def league_view(league, players):
    """Full league payload: teams with resolved rosters, schedule, standings."""
    scoring = league.get("scoring", "ppr")
    teams = []
    for team in league["teams"]:
        roster = []
        for pid in team["roster"]:
            player = players.get(pid)
            if player:
                roster.append(player_summary(player, scoring))
            else:
                roster.append({"id": pid, "name": pid, "position": "",
                               "team": "", "headshot_url": "", "points": 0})
        teams.append({
            "id": team["id"],
            "name": team["name"],
            "roster_ids": list(team["roster"]),
            "roster": roster,
        })
    weeks = [w["week"] for w in league["schedule"]]
    return {
        "id": league["id"],
        "name": league["name"],
        "season": league["season"],
        "scoring": scoring,
        "created_at": league.get("created_at"),
        "teams": teams,
        "schedule": league["schedule"],
        "standings": league_standings(league, players),
        "weeks": weeks,
    }


# --------------------------------------------------------------------------
# League store - persists leagues to a JSON file on disk
# --------------------------------------------------------------------------

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".data"
)
LEAGUES_PATH = os.path.join(DATA_DIR, "leagues.json")


def _new_id():
    return secrets.token_hex(4)


def _now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class LeagueStore:
    """Thread-safe CRUD for fantasy leagues backed by a single JSON file."""

    def __init__(self, path=LEAGUES_PATH):
        self.path = path
        self._lock = threading.Lock()
        self._leagues = {}
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._load()

    def _load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            for league in data.get("leagues", []):
                self._leagues[league["id"]] = league
        except (json.JSONDecodeError, KeyError, OSError):
            # A corrupt or unreadable file shouldn't crash the server; start
            # empty and let the next save rewrite it cleanly.
            self._leagues = {}

    def _save(self):
        """Write all leagues to disk. Caller must hold the lock."""
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"leagues": list(self._leagues.values())}, fh, indent=2)
        os.replace(tmp, self.path)

    def list(self):
        with self._lock:
            return [
                {"id": lg["id"], "name": lg["name"], "season": lg["season"],
                 "scoring": lg["scoring"], "team_count": len(lg["teams"]),
                 "created_at": lg.get("created_at")}
                for lg in sorted(self._leagues.values(),
                                 key=lambda l: l.get("created_at") or "",
                                 reverse=True)
            ]

    def get(self, league_id):
        with self._lock:
            return self._leagues.get(league_id)

    def create(self, name, season, scoring, team_names):
        name = (name or "").strip() or "Untitled League"
        scoring = (scoring or "ppr").lower()
        if scoring not in SCORING_FIELD:
            scoring = "ppr"
        clean_names = [n.strip() for n in team_names if n and n.strip()]
        if len(clean_names) < 2:
            raise ValueError("a league needs at least 2 teams")
        if len(clean_names) > 16:
            raise ValueError("a league can have at most 16 teams")
        teams = [{"id": _new_id(), "name": n, "roster": []}
                 for n in clean_names]
        league = {
            "id": _new_id(),
            "name": name,
            "season": int(season),
            "scoring": scoring,
            "created_at": _now_iso(),
            "teams": teams,
            "schedule": generate_schedule([t["id"] for t in teams]),
        }
        with self._lock:
            self._leagues[league["id"]] = league
            self._save()
        return league

    def set_roster(self, league_id, team_id, player_ids):
        with self._lock:
            league = self._leagues.get(league_id)
            if league is None:
                raise KeyError("league not found")
            team = next((t for t in league["teams"] if t["id"] == team_id), None)
            if team is None:
                raise KeyError("team not found")
            # De-dupe while preserving order.
            seen = set()
            roster = []
            for pid in player_ids:
                if pid and pid not in seen:
                    seen.add(pid)
                    roster.append(pid)
            team["roster"] = roster
            self._save()
            return league

    def delete(self, league_id):
        with self._lock:
            existed = self._leagues.pop(league_id, None) is not None
            if existed:
                self._save()
            return existed


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
LEAGUES = LeagueStore()

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

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError("request body is not valid JSON")
        if not isinstance(data, dict):
            raise ValueError("request body must be a JSON object")
        return data

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

        if path == "/api/leagues":
            self._send_json({"leagues": LEAGUES.list()})
            return

        if path.startswith("/api/leagues/"):
            parts = path[len("/api/leagues/"):].split("/")
            league = LEAGUES.get(parts[0])
            if league is None:
                self._send_error_json(404, "league not found")
                return
            players = DATA.players(league["season"])
            if len(parts) == 1:
                self._send_json(league_view(league, players))
                return
            if len(parts) == 2 and parts[1] == "scoreboard":
                week_raw = params.get("week", [None])[0]
                if not week_raw:
                    self._send_error_json(400, "week is required")
                    return
                self._send_json(league_scoreboard(league, players, int(week_raw)))
                return
            self._send_error_json(404, "unknown endpoint")
            return

        self._send_error_json(404, "unknown endpoint")

    # -- API routes: POST / DELETE ----------------------------------------

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if not path.startswith("/api/"):
                self._send_error_json(404, "unknown endpoint")
                return
            self._handle_api_post(path, self._read_json_body())
        except ValueError as exc:
            self._send_error_json(400, str(exc))
        except KeyError as exc:
            self._send_error_json(404, exc.args[0] if exc.args else "not found")
        except urllib.error.HTTPError as exc:
            self._send_error_json(502, f"upstream data error ({exc.code})")
        except urllib.error.URLError as exc:
            self._send_error_json(502, f"could not reach data source: {exc.reason}")
        except BrokenPipeError:
            pass
        except Exception as exc:  # pragma: no cover - defensive
            self._send_error_json(500, f"server error: {exc}")

    def _handle_api_post(self, path, body):
        if path == "/api/leagues":
            league = LEAGUES.create(
                name=body.get("name", ""),
                season=body.get("season") or DATA.default_season(),
                scoring=body.get("scoring", "ppr"),
                team_names=body.get("teams", []),
            )
            players = DATA.players(league["season"])
            self._send_json(league_view(league, players), status=201)
            return

        if path.startswith("/api/leagues/") and path.endswith("/roster"):
            league_id = path[len("/api/leagues/"):-len("/roster")]
            team_id = body.get("team_id")
            if not team_id:
                raise ValueError("team_id is required")
            league = LEAGUES.set_roster(
                league_id, team_id, body.get("player_ids", []))
            players = DATA.players(league["season"])
            self._send_json(league_view(league, players))
            return

        self._send_error_json(404, "unknown endpoint")

    def do_DELETE(self):
        path = urlparse(self.path).path
        try:
            if path.startswith("/api/leagues/") and "/" not in path[len("/api/leagues/"):]:
                league_id = path[len("/api/leagues/"):]
                if LEAGUES.delete(league_id):
                    self._send_json({"deleted": league_id})
                else:
                    self._send_error_json(404, "league not found")
                return
            self._send_error_json(404, "unknown endpoint")
        except BrokenPipeError:
            pass
        except Exception as exc:  # pragma: no cover - defensive
            self._send_error_json(500, f"server error: {exc}")

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
