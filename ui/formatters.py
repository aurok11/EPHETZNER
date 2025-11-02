"""Formatting helpers for rich-rendered CLI output."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich import box
from rich.table import Table

from ephetzner_core.localization import _

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from ephetzner_core import AppConfig

_SECRET_PLACEHOLDER = "•••••"


def config_summary_table(config: "AppConfig") -> Table:
    """Return a Rich table summarising the current application configuration."""

    table = Table(title=_("Configuration"), box=box.ROUNDED, show_header=False)
    table.add_column(_("Key"), style="bold cyan")
    table.add_column(_("Value"), overflow="fold")

    for label, value, secret in _iter_config_fields(config):
        table.add_row(label, _format_value(value, secret))
    return table


def _iter_config_fields(config: "AppConfig"):
    """Yield tuples describing configuration fields for summary rendering."""

    mapping = (
        (_("Hetzner API token"), config.hetzner_api_token, True),
        (_("DuckDNS token"), config.duckdns_token, True),
        (_("DuckDNS subdomain"), config.duckdns_subdomain, False),
        (_("S3 endpoint"), config.s3_endpoint, False),
        (_("S3 access key"), config.s3_access_key, True),
        (_("S3 secret key"), config.s3_secret_key, True),
        (_("Authorized SSH public key"), config.ssh_public_key, False),
    )
    for item in mapping:
        yield item


def _format_value(value: str | None, secret: bool) -> str:
    """Return formatted configuration value for display."""

    if not value:
        return "[dim]{placeholder}[/dim]".format(placeholder=_("n/a"))
    if secret:
        return _SECRET_PLACEHOLDER
    return value
