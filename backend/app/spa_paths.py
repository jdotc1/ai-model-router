"""Constrain static SPA asset requests to their canonical directory."""

from pathlib import Path


def resolve_spa_asset(static_dir: str | Path, requested_path: str) -> Path:
    root = Path(static_dir).resolve()
    target = (root / requested_path).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Static asset path escapes its directory")
    return target
