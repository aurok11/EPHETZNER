"""Compatibility layer for ``hcloud.exceptions``."""

from __future__ import annotations

from .client import APIException

__all__ = ["APIException"]
