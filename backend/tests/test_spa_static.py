"""Security regression tests for SPA static-file path containment."""

from pathlib import Path

import pytest
from fastapi import HTTPException

from app import server


def test_spa_serves_files_within_static_root(tmp_path, monkeypatch):
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    asset = static / "assets" / "main.js"
    asset.write_text("console.log('ok')", encoding="utf-8")
    monkeypatch.setattr(server, "STATIC_DIR", str(static))

    assert Path(server._resolve_static_asset("assets/main.js")) == asset
    assert Path(server._resolve_static_asset("index.html")) == static / "index.html"


@pytest.mark.parametrize("requested", [
    "../secrets.env",
    "../../secrets.env",
    "../static-other/private.env",
    "/etc/passwd",
])
def test_spa_rejects_traversal_and_absolute_paths(tmp_path, monkeypatch, requested):
    static = tmp_path / "static"
    static.mkdir()
    monkeypatch.setattr(server, "STATIC_DIR", str(static))

    with pytest.raises(HTTPException) as exc:
        server._resolve_static_asset(requested)
    assert exc.value.status_code == 403


def test_spa_rejects_symlinks_to_files_outside_static_root(tmp_path, monkeypatch):
    static = tmp_path / "static"
    static.mkdir()
    outside = tmp_path / "private.env"
    outside.write_text("synthetic-test-value", encoding="utf-8")
    (static / "link.env").symlink_to(outside)
    monkeypatch.setattr(server, "STATIC_DIR", str(static))

    with pytest.raises(HTTPException) as exc:
        server._resolve_static_asset("link.env")
    assert exc.value.status_code == 403
