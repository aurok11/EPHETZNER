"""Subpackage with CLI command implementations for ephetzner."""

from __future__ import annotations

import typer

from . import configure, create, delete


def register(app: typer.Typer) -> None:
    """Register all CLI commands on the provided Typer application."""

    create.register(app)
    delete.register(app)
    configure.register(app)
