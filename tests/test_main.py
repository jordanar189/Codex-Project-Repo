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
