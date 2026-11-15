"""Regression tests for confinement of assets served by the SPA fallback."""

from urllib.parse import unquote

import pytest
from fastapi import HTTPException

from app.static_paths import resolve_static_asset


def test_static_asset_and_spa_fallback_remain_within_root(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    asset = static / "app.js"
    asset.write_text("// public asset")

    assert resolve_static_asset(str(static), "app.js") == asset
    assert resolve_static_asset(str(static), "nested/missing.js") == static / "nested/missing.js"


@pytest.mark.parametrize("path", ["../private.env", "%2e%2e%2fprivate.env", "../../private.env", "/etc/passwd"])
def test_static_asset_rejects_path_traversal(tmp_path, path):
    static = tmp_path / "static"
    static.mkdir()
    candidate = unquote(path)  # ASGI routing receives a URL-decoded path.

    with pytest.raises(HTTPException) as error:
        resolve_static_asset(str(static), candidate)
    assert error.value.status_code == 403


def test_static_asset_rejects_sibling_prefix_and_symlink_escape(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    outside = tmp_path / "static_backup"
    outside.mkdir()
    (outside / "secret.env").write_text("synthetic-only")
    (static / "link.env").symlink_to(outside / "secret.env")

    for path in ("../static_backup/secret.env", "link.env"):
        with pytest.raises(HTTPException) as error:
            resolve_static_asset(str(static), path)
        assert error.value.status_code == 403
