"""Lightweight Hetzner Cloud client compatible with the real ``hcloud`` API surface used here."""

from __future__ import annotations

from .client import APIException, Client

__all__ = ["APIException", "Client"]
