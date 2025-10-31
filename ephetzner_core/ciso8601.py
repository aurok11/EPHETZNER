"""Minimal ciso8601 compatibility shim for environments without native extension."""

from __future__ import annotations

from datetime import datetime


def parse_datetime(value: str) -> datetime:
    """Parse ISO8601 datetime string using the standard library."""

    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)
