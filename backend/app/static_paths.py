"""Resolve SPA assets without allowing access outside the deployed frontend."""

from pathlib import Path

from fastapi import HTTPException


def resolve_static_asset(static_dir: str, requested_path: str) -> Path:
    """Reject traversal and symlinks escaping the canonical static directory."""
    root = Path(static_dir).resolve()
    target = (root / requested_path).resolve()
    if not target.is_relative_to(root):
        raise HTTPException(status_code=403, detail="Access denied")
    return target
