"""Entry point for the ephetzner CLI."""

from __future__ import annotations

import typer

from commands import register as register_commands


app = typer.Typer(help="Ephemeral Hetzner workspace manager")
register_commands(app)


def main() -> None:
    """Execute the Typer application."""

    app()


if __name__ == "__main__":
    main()
