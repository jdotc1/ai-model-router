"""Contain SPA asset lookups within the bundled static directory."""

from pathlib import Path, PureWindowsPath


def resolve_static_asset(static_dir: str, request_path: str) -> Path:
    """Resolve a requested asset, refusing traversal, absolute paths and symlink escapes."""
    if (
        ".." in request_path.replace("\\", "/").split("/")
        or Path(request_path).is_absolute()
        or PureWindowsPath(request_path).drive
    ):
        raise ValueError("Static asset path escapes the document root")

    root = Path(static_dir).resolve()
    target = (root / request_path).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Static asset path escapes the document root")
    return target
