"""Interactive questionary-based menus for the ephetzner CLI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import questionary
from rich.console import Console

from ephetzner_core import AppConfig, with_overrides
from ui.formatters import config_summary_table

_PROMPT_LOOP_NOTE = (
    "Wprowadź wymagane dane. Możesz pozostawić wartość pustą, aby pominąć/pozostawić bez zmian."
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

        suffix = " (opcjonalne)" if self.optional else ""
        if self.secret and current_value:
            return f"{self.label}{suffix} – pozostaw puste, by zachować obecną wartość"
        if current_value:
            return f"{self.label}{suffix} (obecnie: {self._short_value_hint(current_value)})"
        return f"{self.label}{suffix}"

    def _short_value_hint(self, value: str) -> str:
        """Return hint used when displaying a non-secret existing value."""

        if self.secret:
            return "ustawione"
        if len(value) <= 12:
            return value
        return f"{value[:12]}…"


_FIELDS: tuple[_ConfigField, ...] = (
    _ConfigField("hetzner_api_token", "Hetzner API token", secret=True, optional=False),
    _ConfigField("duckdns_token", "DuckDNS token", secret=True),
    _ConfigField("duckdns_subdomain", "Domyślna subdomena DuckDNS", secret=False),
    _ConfigField("s3_endpoint", "S3 endpoint URL", secret=False),
    _ConfigField("s3_access_key", "S3 access key", secret=True),
    _ConfigField("s3_secret_key", "S3 secret key", secret=True),
)


def prompt_app_config(config: AppConfig, console: Optional[Console] = None) -> AppConfig:
    """Prompt user for configuration values, returning an updated config object."""

    console = console or Console()
    console.print("[bold]Konfiguracja ephetzner[/bold]")
    console.print(_PROMPT_LOOP_NOTE)

    current = config
    while True:
        overrides: dict[str, Optional[str]] = {}
        for field in _FIELDS:
            overrides[field.name] = _prompt_field(field, current)

        updated = with_overrides(current, **overrides)
        console.print(config_summary_table(updated))
        confirmed = questionary.confirm(
            "Czy zaakceptować powyższą konfigurację?",
            default=True,
        ).ask()
        if confirmed:
            return updated
        console.print("[yellow]Edytujemy konfigurację ponownie...[/yellow]")
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
