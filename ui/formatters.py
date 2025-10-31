"""Formatting helpers for rich-rendered CLI output."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich import box
from rich.table import Table

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from ephetzner_core import AppConfig

_SECRET_PLACEHOLDER = "•••••"


def config_summary_table(config: "AppConfig") -> Table:
    """Return a Rich table summarising the current application configuration."""

    table = Table(title="Konfiguracja", box=box.ROUNDED, show_header=False)
    table.add_column("Klucz", style="bold cyan")
    table.add_column("Wartość", overflow="fold")

    for label, value, secret in _iter_config_fields(config):
        table.add_row(label, _format_value(value, secret))
    return table


def _iter_config_fields(config: "AppConfig"):
    """Yield tuples describing configuration fields for summary rendering."""

    mapping = (
        ("Hetzner API token", config.hetzner_api_token, True),
        ("DuckDNS token", config.duckdns_token, True),
        ("S3 endpoint", config.s3_endpoint, False),
        ("S3 access key", config.s3_access_key, True),
        ("S3 secret key", config.s3_secret_key, True),
    )
    for item in mapping:
        yield item


def _format_value(value: str | None, secret: bool) -> str:
    """Return formatted configuration value for display."""

    if not value:
        return "[dim]n/d[/dim]"
    if secret:
        return _SECRET_PLACEHOLDER
    return value
