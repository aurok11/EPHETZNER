"""Entry point for the ephetzner CLI."""

from __future__ import annotations

import sys

import typer

from commands import register as register_commands
from ephetzner_core.localization import _, initialize_locale


def _build_app() -> typer.Typer:
    """Create the Typer application after initialising localisation."""

    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    initialize_locale(interactive=interactive)
    application = typer.Typer(help=_("Ephemeral Hetzner workspace manager"))
    register_commands(application)
    return application


def main() -> None:
    """Execute the Typer application."""

    app = _build_app()
    app()


if __name__ == "__main__":
    main()
