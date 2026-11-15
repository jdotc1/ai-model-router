"""Static SPA paths must remain inside their canonical asset directory."""

import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote

from app.spa_paths import resolve_spa_asset


class SpaPathSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "static"
        self.root.mkdir()

    def test_normal_asset_and_index_paths_are_allowed(self):
        self.assertEqual(resolve_spa_asset(self.root, "assets/main.js"), self.root / "assets/main.js")
        self.assertEqual(resolve_spa_asset(self.root, "index.html"), self.root / "index.html")

    def test_parent_and_percent_decoded_traversal_are_refused(self):
        for path in ("../secret.env", "../../model_router.db", "%2e%2e%2fsecret.env"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                resolve_spa_asset(self.root, unquote(path))

    def test_sibling_prefix_does_not_count_as_inside_static_root(self):
        sibling = Path(self.temp.name) / "static-private"
        sibling.mkdir()
        with self.assertRaises(ValueError):
            resolve_spa_asset(self.root, "../static-private/secret")

    def test_symlink_target_outside_root_is_refused(self):
        (Path(self.temp.name) / "secret.env").write_text("not a real secret")
        (self.root / "outside").symlink_to(Path(self.temp.name), target_is_directory=True)
        with self.assertRaises(ValueError):
            resolve_spa_asset(self.root, "outside/secret.env")


if __name__ == "__main__":
    unittest.main()
