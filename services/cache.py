"""Cache utilities for persisting ephemeral data between CLI runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

CACHE_DIR_POSIX = Path("~/.cache/hetzner-ephemeral").expanduser()
CACHE_DIR_WINDOWS = Path("%LOCALAPPDATA%/HetznerEphemeral").expanduser()


def default_cache_dir() -> Path:
    """Return platform-aware cache directory path."""
    if Path.home().drive:
        # Windows path detection
        return CACHE_DIR_WINDOWS
    return CACHE_DIR_POSIX


def ensure_cache_dir(path: Optional[Path] = None) -> Path:
    """Create cache directory if missing and return its path."""
    target = path or default_cache_dir()
    target.mkdir(parents=True, exist_ok=True)
    return target


def cache_file(name: str, directory: Optional[Path] = None) -> Path:
    """Return full Path for a cache file under the cache directory."""
    folder = ensure_cache_dir(directory)
    return folder / name


def read_json(name: str) -> Optional[Any]:
    """Read JSON payload from cache file when available."""
    file_path = cache_file(name)
    if not file_path.exists():
        return None
    try:
        import json

        return json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_json(name: str, payload: Any) -> None:
    """Persist JSON payload into cache file."""
    import json

    file_path = cache_file(name)
    file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_cache(name: Optional[str] = None) -> None:
    """Remove specific cache file or entire cache directory."""
    target_dir = ensure_cache_dir()
    if name:
        try:
            (target_dir / name).unlink(missing_ok=True)
        except OSError:
            pass
        return
    for item in target_dir.iterdir():
        if item.is_file():
            try:
                item.unlink()
            except OSError:
                continue
