"""Interactive questionary-based menus for the ephetzner CLI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import questionary
from rich.console import Console

from ephetzner_core import AppConfig, with_overrides
from ephetzner_core.localization import _
from ui.formatters import config_summary_table

_PROMPT_LOOP_NOTE = (
    "Provide required values. Leave blank to skip or keep the current value."
)


@dataclass(frozen=True)
class _ConfigField:
    """Description of a configuration field prompt."""

    name: str
    label: str
    secret: bool = False
    optional: bool = True

    def message(self, current_value: Optional[str]) -> str:
        """Build a prompt message including optionality hints."""

        label_text = _(self.label)
        suffix = _(" (optional)") if self.optional else ""
        if self.secret and current_value:
            template = _("{label}{suffix} – leave blank to keep existing value")
            return template.format(label=label_text, suffix=suffix)
        if current_value:
            template = _("{label}{suffix} (current: {value})")
            return template.format(
                label=label_text,
                suffix=suffix,
                value=self._short_value_hint(current_value),
            )
        template = _("{label}{suffix}")
        return template.format(label=label_text, suffix=suffix)

    def _short_value_hint(self, value: str) -> str:
        """Return hint used when displaying a non-secret existing value."""

        if self.secret:
            return _("set")
        if len(value) <= 12:
            return value
        return f"{value[:12]}…"


_FIELDS: tuple[_ConfigField, ...] = (
    _ConfigField("hetzner_api_token", "Hetzner API token", secret=True, optional=False),
    _ConfigField("duckdns_token", "DuckDNS token", secret=True),
    _ConfigField("duckdns_subdomain", "DuckDNS default subdomain", secret=False),
    _ConfigField("s3_endpoint", "S3 endpoint URL", secret=False),
    _ConfigField("s3_access_key", "S3 access key", secret=True),
    _ConfigField("s3_secret_key", "S3 secret key", secret=True),
    _ConfigField("ssh_public_key", "Authorized SSH public key", secret=False),
)


def prompt_app_config(config: AppConfig, console: Optional[Console] = None) -> AppConfig:
    """Prompt user for configuration values, returning an updated config object."""

    console = console or Console()
    console.print(_("[bold]ephetzner configuration[/bold]"))
    console.print(_(_PROMPT_LOOP_NOTE))

    current = config
    while True:
        overrides: dict[str, Optional[str]] = {}
        for field in _FIELDS:
            overrides[field.name] = _prompt_field(field, current)

        updated = with_overrides(current, **overrides)
        console.print(config_summary_table(updated))
        confirmed = questionary.confirm(
            _("Accept the configuration above?"),
            default=True,
        ).ask()
        if confirmed:
            return updated
        console.print(_("[yellow]Reopening configuration prompts...[/yellow]"))
        current = updated


def _prompt_field(field: _ConfigField, config: AppConfig) -> Optional[str]:
    """Prompt user for a single configuration field."""

    current_value = getattr(config, field.name)
    asker: Callable[..., Optional[str]]
    kwargs: dict[str, object] = {}
    if field.secret:
        asker = questionary.password
    else:
        asker = questionary.text
        if current_value:
            kwargs["default"] = current_value

    answer = asker(field.message(current_value), **kwargs).ask()
    if answer is None:
        return current_value

    normalized = answer.strip()
    if normalized == "":
        return current_value if field.secret else None
    return normalized
