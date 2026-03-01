import unittest
from pathlib import Path

from src import main


class MainTests(unittest.TestCase):
    def test_game_assets_exist(self):
        src_dir = Path(__file__).resolve().parents[1] / "src"
        self.assertTrue((src_dir / "index.html").exists())
        self.assertTrue((src_dir / "style.css").exists())
        self.assertTrue((src_dir / "game.js").exists())

    def test_main_module_has_entrypoint(self):
        self.assertTrue(callable(main.main))


if __name__ == "__main__":
    unittest.main()
