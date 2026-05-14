import os
import shutil
import tempfile
import unittest
from pathlib import Path

from src.main import (
    parse_player_stats,
    season_totals,
    half_ppr,
    player_summary,
    search_players,
    rank_players,
    player_detail,
    generate_schedule,
    team_week_score,
    league_scoreboard,
    league_standings,
    league_view,
    LeagueStore,
    STAT_FIELDS,
)
import src.main as main_module

# A tiny nflverse-style fixture: header plus a few REG rows and one POST row
# that should be filtered out. Columns mirror stats_player_week_<season>.csv;
# only the fields the app reads need realistic values.
HEADER = (
    "player_id,player_name,player_display_name,position,position_group,"
    "headshot_url,season,week,season_type,team,opponent_team,"
    "completions,attempts,passing_yards,passing_tds,passing_interceptions,"
    "carries,rushing_yards,rushing_tds,receptions,targets,receiving_yards,"
    "receiving_tds,fantasy_points,fantasy_points_ppr"
)

# Field index lookup so test rows stay readable.
COLS = HEADER.split(",")


def row(**kw):
    values = {c: "" for c in COLS}
    values.update({k: str(v) for k, v in kw.items()})
    return ",".join(values[c] for c in COLS)


SAMPLE_CSV = "\n".join([
    HEADER,
    # QB: two regular-season games.
    row(player_id="QB1", player_display_name="Test QB", position="QB",
        position_group="QB", season=2024, week=1, season_type="REG", team="AAA",
        opponent_team="BBB", completions=20, attempts=30, passing_yards=300,
        passing_tds=3, passing_interceptions=1, fantasy_points=24.0,
        fantasy_points_ppr=24.0),
    row(player_id="QB1", player_display_name="Test QB", position="QB",
        position_group="QB", season=2024, week=2, season_type="REG", team="AAA",
        opponent_team="CCC", completions=25, attempts=35, passing_yards=250,
        passing_tds=1, passing_interceptions=2, fantasy_points=10.0,
        fantasy_points_ppr=10.0),
    # WR: one regular-season game with receptions (PPR should differ).
    row(player_id="WR1", player_display_name="Test WR", position="WR",
        position_group="WR", season=2024, week=1, season_type="REG", team="AAA",
        opponent_team="BBB", receptions=8, targets=11, receiving_yards=120,
        receiving_tds=1, fantasy_points=18.0, fantasy_points_ppr=26.0),
    # Postseason row for QB1 - must be ignored by the parser.
    row(player_id="QB1", player_display_name="Test QB", position="QB",
        position_group="QB", season=2024, week=1, season_type="POST", team="AAA",
        opponent_team="DDD", passing_yards=999, fantasy_points=99.0,
        fantasy_points_ppr=99.0),
])


class ParsingTests(unittest.TestCase):
    def setUp(self):
        self.players = parse_player_stats(SAMPLE_CSV)

    def test_groups_players_by_id(self):
        self.assertEqual({"QB1", "WR1"}, set(self.players))

    def test_excludes_postseason_rows(self):
        # QB1 has 2 REG games; the POST row must not be included.
        self.assertEqual(2, len(self.players["QB1"]["games"]))

    def test_games_sorted_by_week(self):
        weeks = [g["week"] for g in self.players["QB1"]["games"]]
        self.assertEqual([1, 2], weeks)

    def test_player_metadata_captured(self):
        wr = self.players["WR1"]
        self.assertEqual("Test WR", wr["name"])
        self.assertEqual("WR", wr["position"])
        self.assertEqual("AAA", wr["team"])

    def test_blank_cells_parse_as_zero(self):
        # The WR row leaves passing_yards blank.
        self.assertEqual(0, self.players["WR1"]["games"][0]["passing_yards"])

    def test_every_stat_field_present_on_each_game(self):
        for player in self.players.values():
            for game in player["games"]:
                for field in STAT_FIELDS:
                    self.assertIn(field, game)


class FantasyMathTests(unittest.TestCase):
    def test_half_ppr_adds_half_point_per_reception(self):
        game = {"fantasy_points": 18.0, "receptions": 8}
        self.assertEqual(22.0, half_ppr(game))

    def test_half_ppr_with_no_receptions_matches_standard(self):
        game = {"fantasy_points": 24.0, "receptions": 0}
        self.assertEqual(24.0, half_ppr(game))

    def test_season_totals_sum_counting_stats(self):
        players = parse_player_stats(SAMPLE_CSV)
        totals = season_totals(players["QB1"]["games"])
        self.assertEqual(2, totals["games_played"])
        self.assertEqual(550, totals["passing_yards"])
        self.assertEqual(4, totals["passing_tds"])
        self.assertEqual(34.0, totals["fantasy_points_ppr"])

    def test_player_summary_points_follow_scoring(self):
        players = parse_player_stats(SAMPLE_CSV)
        wr = players["WR1"]
        self.assertEqual(18.0, player_summary(wr, "standard")["points"])
        self.assertEqual(26.0, player_summary(wr, "ppr")["points"])
        self.assertEqual(22.0, player_summary(wr, "half")["points"])

    def test_points_per_game(self):
        players = parse_player_stats(SAMPLE_CSV)
        summary = player_summary(players["QB1"], "ppr")
        self.assertEqual(17.0, summary["points_per_game"])


class SearchAndRankingTests(unittest.TestCase):
    def setUp(self):
        self.players = parse_player_stats(SAMPLE_CSV)

    def test_search_filters_by_query(self):
        results = search_players(self.players, query="test wr")
        self.assertEqual(1, len(results))
        self.assertEqual("WR1", results[0]["id"])

    def test_search_filters_by_position(self):
        results = search_players(self.players, position="QB")
        self.assertEqual(["QB1"], [r["id"] for r in results])

    def test_search_sorted_by_points_desc(self):
        # WR1 has 26 PPR, QB1 has 34 PPR total -> QB1 first.
        results = search_players(self.players, scoring="ppr")
        self.assertEqual(["QB1", "WR1"], [r["id"] for r in results])

    def test_season_rankings_assign_rank_numbers(self):
        ranked = rank_players(self.players, scope="season", scoring="ppr")
        self.assertEqual(1, ranked[0]["rank"])
        self.assertEqual("QB1", ranked[0]["id"])
        self.assertEqual(2, ranked[1]["rank"])

    def test_week_rankings_use_single_game(self):
        ranked = rank_players(self.players, scope="week", week=1, scoring="ppr")
        # Week 1: WR1 = 26 PPR, QB1 = 24 PPR -> WR1 ranked first.
        self.assertEqual("WR1", ranked[0]["id"])
        self.assertEqual("BBB", ranked[0]["opponent"])

    def test_week_rankings_skip_players_without_that_week(self):
        ranked = rank_players(self.players, scope="week", week=2, scoring="ppr")
        self.assertEqual(["QB1"], [r["id"] for r in ranked])

    def test_position_filter_in_rankings(self):
        ranked = rank_players(self.players, scope="season", position="WR")
        self.assertEqual(["WR1"], [r["id"] for r in ranked])


class PlayerDetailTests(unittest.TestCase):
    def test_detail_includes_totals_and_games(self):
        players = parse_player_stats(SAMPLE_CSV)
        detail = player_detail(players["QB1"], scoring="ppr")
        self.assertEqual("Test QB", detail["name"])
        self.assertEqual(2, len(detail["games"]))
        self.assertEqual(550, detail["season_totals"]["passing_yards"])
        self.assertEqual("ppr", detail["scoring"])


def make_league(scoring="ppr"):
    """A two-team league: Alpha rosters QB1, Bravo rosters WR1."""
    return {
        "id": "lg1",
        "name": "Test League",
        "season": 2024,
        "scoring": scoring,
        "created_at": "2026-01-01T00:00:00+00:00",
        "teams": [
            {"id": "A", "name": "Alpha", "roster": ["QB1"]},
            {"id": "B", "name": "Bravo", "roster": ["WR1"]},
        ],
        "schedule": generate_schedule(["A", "B"]),
    }


class ScheduleTests(unittest.TestCase):
    def test_even_teams_play_full_round_robin(self):
        schedule = generate_schedule(["A", "B", "C", "D"])
        self.assertEqual(3, len(schedule))  # n-1 weeks
        pairs = set()
        for week in schedule:
            self.assertEqual(2, len(week["matchups"]))
            self.assertEqual([], week["byes"])
            for a, b in week["matchups"]:
                pairs.add(frozenset((a, b)))
        # Every team faces every other team exactly once.
        self.assertEqual(6, len(pairs))

    def test_odd_teams_get_one_bye_per_week(self):
        schedule = generate_schedule(["A", "B", "C"])
        self.assertEqual(3, len(schedule))
        for week in schedule:
            self.assertEqual(1, len(week["matchups"]))
            self.assertEqual(1, len(week["byes"]))
        # Each team sits out exactly once.
        byes = [t for week in schedule for t in week["byes"]]
        self.assertEqual({"A", "B", "C"}, set(byes))
        self.assertEqual(3, len(byes))


class TeamScoringTests(unittest.TestCase):
    def setUp(self):
        self.players = parse_player_stats(SAMPLE_CSV)

    def test_team_week_score_sums_roster(self):
        # Week 1 PPR: QB1 = 24, WR1 = 26.
        total, breakdown = team_week_score(
            self.players, ["QB1", "WR1"], 1, "ppr")
        self.assertEqual(50.0, total)
        self.assertEqual(2, len(breakdown))
        self.assertTrue(all(p["played"] for p in breakdown))
        # Breakdown is sorted high-to-low.
        self.assertEqual("WR1", breakdown[0]["id"])

    def test_team_week_score_handles_missing_and_unknown(self):
        # WR1 has no week 2 game; "GHOST" is not a real player id.
        total, breakdown = team_week_score(
            self.players, ["WR1", "GHOST"], 2, "ppr")
        self.assertEqual(0, total)
        self.assertTrue(all(not p["played"] for p in breakdown))

    def test_team_week_score_follows_scoring_setting(self):
        # WR1 week 1: standard 18, PPR 26.
        std, _ = team_week_score(self.players, ["WR1"], 1, "standard")
        ppr, _ = team_week_score(self.players, ["WR1"], 1, "ppr")
        self.assertEqual(18.0, std)
        self.assertEqual(26.0, ppr)


class LeagueResultTests(unittest.TestCase):
    def setUp(self):
        self.players = parse_player_stats(SAMPLE_CSV)
        self.league = make_league()

    def test_scoreboard_reports_matchup_scores(self):
        board = league_scoreboard(self.league, self.players, 1)
        self.assertEqual(1, len(board["matchups"]))
        matchup = board["matchups"][0]
        self.assertTrue(matchup["played"])
        self.assertEqual(24.0, matchup["home"]["points"])  # Alpha / QB1
        self.assertEqual(26.0, matchup["away"]["points"])  # Bravo / WR1

    def test_standings_award_win_to_higher_score(self):
        table = league_standings(self.league, self.players)
        top = table[0]
        self.assertEqual("Bravo", top["name"])  # WR1 outscored QB1
        self.assertEqual(1, top["wins"])
        self.assertEqual(0, top["losses"])
        self.assertEqual(26.0, top["points_for"])
        self.assertEqual(24.0, top["points_against"])
        self.assertEqual(1, top["rank"])

    def test_standings_skip_weeks_with_no_games(self):
        # Add a week nobody has stats for; it must not count.
        self.league["schedule"] = [
            {"week": 1, "matchups": [["A", "B"]], "byes": []},
            {"week": 99, "matchups": [["A", "B"]], "byes": []},
        ]
        table = league_standings(self.league, self.players)
        self.assertTrue(all(row["games"] == 1 for row in table))

    def test_league_view_resolves_rosters(self):
        view = league_view(self.league, self.players)
        self.assertEqual([1], view["weeks"])
        alpha = next(t for t in view["teams"] if t["name"] == "Alpha")
        self.assertEqual(["QB1"], alpha["roster_ids"])
        self.assertEqual("Test QB", alpha["roster"][0]["name"])


class LeagueStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "leagues.json")
        self.store = LeagueStore(self.path)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_create_generates_ids_schedule_and_empty_rosters(self):
        lg = self.store.create("My League", 2024, "ppr", ["A", "B", "C", "D"])
        self.assertEqual("My League", lg["name"])
        self.assertEqual(4, len(lg["teams"]))
        self.assertEqual(3, len(lg["schedule"]))
        self.assertTrue(all(t["roster"] == [] for t in lg["teams"]))
        self.assertTrue(all(t["id"] for t in lg["teams"]))

    def test_create_rejects_too_few_teams(self):
        with self.assertRaises(ValueError):
            self.store.create("X", 2024, "ppr", ["only one"])

    def test_create_falls_back_to_ppr_for_unknown_scoring(self):
        lg = self.store.create("L", 2024, "bogus", ["A", "B"])
        self.assertEqual("ppr", lg["scoring"])

    def test_set_roster_dedupes_and_persists(self):
        lg = self.store.create("L", 2024, "ppr", ["A", "B"])
        team_id = lg["teams"][0]["id"]
        updated = self.store.set_roster(lg["id"], team_id, ["p1", "p2", "p1"])
        team = next(t for t in updated["teams"] if t["id"] == team_id)
        self.assertEqual(["p1", "p2"], team["roster"])

    def test_set_roster_unknown_team_raises(self):
        lg = self.store.create("L", 2024, "ppr", ["A", "B"])
        with self.assertRaises(KeyError):
            self.store.set_roster(lg["id"], "nope", ["p1"])

    def test_leagues_persist_across_instances(self):
        lg = self.store.create("Persisted", 2024, "ppr", ["A", "B"])
        reloaded = LeagueStore(self.path)
        again = reloaded.get(lg["id"])
        self.assertIsNotNone(again)
        self.assertEqual("Persisted", again["name"])

    def test_delete_removes_league(self):
        lg = self.store.create("L", 2024, "ppr", ["A", "B"])
        self.assertTrue(self.store.delete(lg["id"]))
        self.assertFalse(self.store.delete(lg["id"]))
        self.assertIsNone(self.store.get(lg["id"]))


class AssetTests(unittest.TestCase):
    def test_web_assets_exist(self):
        web_dir = Path(__file__).resolve().parents[1] / "src" / "web"
        self.assertTrue((web_dir / "index.html").exists())
        self.assertTrue((web_dir / "style.css").exists())
        self.assertTrue((web_dir / "app.js").exists())

    def test_main_module_has_entrypoint(self):
        self.assertTrue(callable(main_module.main))


if __name__ == "__main__":
    unittest.main()
