"""Security regressions for the bundled frontend's static-file handler."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.server import mount_spa


@pytest.mark.asyncio
async def test_spa_static_assets_and_fallback(tmp_path):
    root = tmp_path / "frontend"
    root.mkdir()
    (root / "index.html").write_text("app shell")
    (root / "main.js").write_text("console.log('ok')")
    app = FastAPI()
    assert mount_spa(app, str(root)) is True
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/main.js")).text == "console.log('ok')"
        assert (await client.get("/dashboard")).text == "app shell"


@pytest.mark.asyncio
async def test_spa_rejects_traversal_and_symlinks_outside_static_root(tmp_path):
    root = tmp_path / "frontend"
    root.mkdir()
    (root / "index.html").write_text("app shell")
    (tmp_path / "private.txt").write_text("private")
    (root / "outside.txt").symlink_to(tmp_path / "private.txt")
    app = FastAPI()
    mount_spa(app, str(root))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for path in ["/%2e%2e%2fprivate.txt", "/outside.txt"]:
            response = await client.get(path)
            assert response.status_code in (403, 404), path
            assert "private" not in response.text


def test_spa_without_static_directory_does_not_register_routes(tmp_path):
    app = FastAPI()
    assert mount_spa(app, str(tmp_path / "missing")) is False
    assert not any(route.path == "/{full_path:path}" for route in app.routes)
