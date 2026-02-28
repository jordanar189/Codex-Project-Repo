import unittest
from unittest.mock import patch

from src.main import Hole, Player, calculate_shot_result, create_course


class MainTests(unittest.TestCase):
    def test_create_course_has_9_holes(self):
        holes = create_course(seed=123)
        self.assertEqual(9, len(holes))
        self.assertEqual(1, holes[0].number)
        self.assertTrue(all(30 <= hole.distance <= 90 for hole in holes))

    def test_hazard_reduces_movement(self):
        hole = Hole(number=1, par=3, distance=50, hazard_chance=1.0)
        with patch("src.main.random.randint", side_effect=[0, 10]):
            moved, event = calculate_shot_result(50, hole)
        self.assertEqual(40, moved)
        self.assertIn("Hazard", event)

    def test_player_score_to_par(self):
        player = Player(name="Alex", strokes_per_hole=[3, 4, 6])
        self.assertEqual(13, player.total_strokes())
        self.assertEqual(1, player.score_to_par())


if __name__ == "__main__":
    unittest.main()
