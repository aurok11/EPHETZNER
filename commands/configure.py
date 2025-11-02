"""CLI helpers for managing ephetzner configuration files."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer

from ephetzner_core import resolve_config_path
from ephetzner_core.localization import _

app = typer.Typer()

_TEMPLATE = """[ephetzner]
# s3_endpoint = https://objects.example
# ssh_public_key = ssh-ed25519 AAAA...

[ephetzner.secrets]
# hetzner_api_token =
# duckdns_token =
# s3_access_key =
# s3_secret_key =
"""


def register(app_root: typer.Typer) -> None:
    """Attach configuration-related subcommands to the CLI."""

    app.help = _("Manage ephetzner configuration files")
    app_root.add_typer(app, name="config")


@app.command("init")
def init_config(
    path: Optional[Path] = typer.Option(None, "--path", help="Destination for the ini file"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite when the file already exists"),
) -> None:
    """Create a template configuration file with explanatory comments."""

    destination = (path or resolve_config_path()).expanduser()
    if destination.exists() and not overwrite:
        typer.secho(
            _("Configuration file already exists: {path}").format(path=destination),
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=1)

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(_TEMPLATE, encoding="ascii")

    try:
        os.chmod(destination, 0o600)
    except (PermissionError, NotImplementedError):  # pragma: no cover - platform specific
        pass

    typer.secho(
        _("Template saved to {path}").format(path=destination),
        fg=typer.colors.GREEN,
    )
