import asyncio
import json
import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse
from sqlalchemy import select, desc

from typing import List, Optional

from app.config.settings import get_settings
from app.storage.database import init_db, AsyncSessionLocal
from app.storage.models import RequestRecord
from app.api.routes import router as api_router

import logging
from app.storage.redis_client import init_redis, close_redis

logger = logging.getLogger("model_router.server")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database and seed defaults
    await init_db()
    # Initialize Redis Pub/Sub client if configured (falls back gracefully if unavailable)
    try:
        await init_redis()
    except Exception as e:
        logger.warning(f"Failed to initialize Redis during startup: {e}")
    yield
    # Clean teardown on shutdown
    try:
        await close_redis()
    except Exception:
        pass


app = FastAPI(
    title="Model Router",
    description="Intelligent LLM Request Routing Platform — AI Traffic Control Room",
    version="1.0.0",
    lifespan=lifespan,
)

def setup_cors(app: FastAPI, allowed_origins: Optional[List[str]] = None) -> None:
    """
    Configure CORS middleware on the FastAPI application with credentialed support.
    Permits specified allowed_origins as well as local development origins via regex.
    """
    origins = allowed_origins if allowed_origins is not None else settings.ALLOWED_ORIGINS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# CORS configuration (compliant with credentials)
setup_cors(app)

app.include_router(api_router)


# The live traffic SSE stream endpoint is provided by api_router (/api/traffic/stream).
# Re-export stream_live_traffic for backward compatibility if imported directly.
from app.api.routes import traffic_stream as stream_live_traffic


def mount_spa(app: FastAPI, static_dir: str) -> bool:
    """Mount a bundled frontend without allowing files outside its root."""
    static_root = Path(static_dir).resolve()
    if not static_root.is_dir():
        return False

    assets_dir = static_root / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("docs") or full_path.startswith("openapi.json"):
            raise HTTPException(status_code=404, detail="Not Found")

        target_file = (static_root / full_path).resolve()
        if not target_file.is_relative_to(static_root):
            raise HTTPException(status_code=403, detail="Access denied")
        if target_file.is_file():
            return FileResponse(str(target_file))
        return FileResponse(str(static_root / "index.html"))

    return True


# Serve Bundled Frontend (SPA) if static directory exists
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if not mount_spa(app, STATIC_DIR):
    @app.get("/")
    async def root():
        return {
            "message": "Model Router AI Control Room Backend is active.",
            "docs": "/docs",
            "health": "/api/health",
        }

