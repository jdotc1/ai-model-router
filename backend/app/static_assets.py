"""Resolve SPA asset paths without serving files outside the bundled frontend."""

from pathlib import Path
from urllib.parse import unquote


def resolve_static_asset(static_dir: str | Path, full_path: str) -> Path:
    root = Path(static_dir).resolve()
    try:
        target = (root / unquote(full_path)).resolve()
    except (OSError, RuntimeError) as exc:
        raise ValueError("Invalid static asset path") from exc
    if not target.is_relative_to(root):
        raise ValueError("Static asset escapes the frontend directory")
    return target
