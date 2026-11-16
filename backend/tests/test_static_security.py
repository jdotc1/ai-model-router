from pathlib import Path

import pytest

from app.static_security import resolve_static_asset


def test_normal_assets_remain_within_root(tmp_path: Path):
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    css = static / "assets" / "app.css"
    css.write_text("body {}")
    assert resolve_static_asset(str(static), "assets/app.css") == css
    assert resolve_static_asset(str(static), "unknown/route").is_relative_to(static)


@pytest.mark.parametrize("unsafe", [
    "../.env",
    "assets/../../model_router.db",
    r"..\..\secret",
    "/etc/passwd",
    r"C:\Windows\win.ini",
    "assets/../index.html",
])
def test_traversal_and_absolute_paths_rejected(tmp_path: Path, unsafe: str):
    with pytest.raises(ValueError, match="escapes"):
        resolve_static_asset(str(tmp_path), unsafe)


def test_symlink_escape_rejected(tmp_path: Path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "linked").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="escapes"):
        resolve_static_asset(str(static), "linked/private.txt")
