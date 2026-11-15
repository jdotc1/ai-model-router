"""Regression coverage for the SPA static-file traversal boundary."""

import tempfile
import unittest
from pathlib import Path

from app.static_assets import resolve_static_asset


class StaticAssetPathsTest(unittest.TestCase):
    def test_serves_bundled_assets_and_in_root_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "static"
            (root / "assets").mkdir(parents=True)
            asset = root / "assets" / "app.js"
            asset.write_text("console.log('test')", encoding="utf-8")
            self.assertEqual(resolve_static_asset(root, "assets/app.js"), asset)
            self.assertEqual(resolve_static_asset(root, "assets/../assets/app.js"), asset)

    def test_rejects_traversal_and_sibling_prefix_collision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "static"
            root.mkdir()
            (Path(directory) / ".env").write_text("TEST_ONLY=1", encoding="utf-8")
            sibling = Path(directory) / "static-backup"
            sibling.mkdir()
            (sibling / "secrets.txt").write_text("test", encoding="utf-8")

            for path in ["../.env", "..%2F.env", "%2e%2e%2f.env", "/etc/passwd", "../static-backup/secrets.txt"]:
                with self.subTest(path=path):
                    with self.assertRaises(ValueError):
                        resolve_static_asset(root, path)

    def test_rejects_symlink_to_external_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "static"
            root.mkdir()
            outside = Path(directory) / ".env"
            outside.write_text("TEST_ONLY=1", encoding="utf-8")
            (root / "config.txt").symlink_to(outside)

            with self.assertRaises(ValueError):
                resolve_static_asset(root, "config.txt")


if __name__ == "__main__":
    unittest.main()
