"""Typer command implementing the interactive server creation flow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import questionary
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ephetzner_core import AppConfig, resolve_config
from services.base import ProvisioningRequest, ServerTypeInfo
from services.providers import build_cloud_provider, build_dns_provider
from ui.formatters import config_summary_table

app = typer.Typer(help="Create ephemeral Hetzner workspaces")

EPHEMERAL_LABEL = {"Type": "Ephemeral"}


@dataclass(slots=True)
class CloudInitOptions:
    """Cloud-init configuration describing optional bootstrap script."""

    enabled: bool
    path: Optional[Path]
    runtime: Optional[str]
    content: Optional[str]


@dataclass(slots=True)
class DuckDNSOptions:
    """DuckDNS linking preferences gathered from the user."""

    enabled: bool
    hostname: Optional[str]


def register(app_root: typer.Typer) -> None:
    """Register this module's command with the Typer application."""

    app_root.command("create")(create)


@app.command()
def create(
    name: Optional[str] = typer.Option(None, "--name", help="Server name to provision"),
    project: Optional[str] = typer.Option(None, "--project", help="Hetzner project identifier"),
    server_type: Optional[str] = typer.Option(None, "--server-type", help="Hetzner server type (e.g. cx21)"),
    image: Optional[str] = typer.Option(None, "--image", help="OS image identifier"),
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Skip interactive prompts"),
) -> None:
    """Provision a new ephemeral server based on interactive configuration."""

    console = Console()
    config = resolve_config(interactive=not non_interactive)

    console.print(Panel(config_summary_table(config), title="Konfiguracja środowiska"))
    provider = build_cloud_provider(config)

    selected_type = _resolve_server_type(provider, server_type)
    selected_image = _resolve_image(provider, image)
    server_name = name or questionary.text("Podaj nazwę serwera:").ask()
    if not server_name:
        typer.secho("Nazwa serwera jest wymagana", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    project_id = project or questionary.text(
        "Podaj projekt Hetzner (pozostaw puste, aby użyć domyślnego)", default=""
    ).ask()
    project_id = project_id or "default"

    duckdns_options = _ask_duckdns_options(config)
    cloud_init_options = _ask_cloud_init_options()

    summary = _build_summary_table(
        server_name,
        project_id,
        selected_type,
        selected_image,
        duckdns_options,
        cloud_init_options,
    )
    console.print(Panel(summary, title="Podsumowanie konfiguracji"))

    confirm = questionary.confirm("Czy utworzyć serwer?", default=True).ask()
    if not confirm:
        typer.secho("Operacja anulowana przez użytkownika", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)

    request = ProvisioningRequest(
        name=server_name,
        project=project_id,
        server_type=selected_type.identifier,
        image=selected_image.identifier,
        labels={"Type": "Ephemeral", "Project": project_id},
        cloud_init=cloud_init_options.content,
    )

    try:
        server = provider.create_server(request)
    except NotImplementedError:
        typer.secho(
            "Tworzenie serwera nie jest jeszcze zaimplementowane. Sprawdź roadmapę.",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=1)
    except Exception as exc:  # pragma: no cover - defensive guard
        typer.secho(f"Błąd tworzenia serwera: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    console.print(f"[green]Serwer utworzony pomyślnie: {server.name} ({server.identifier})[/green]")

    if duckdns_options.enabled:
        try:
            dns_provider = build_dns_provider(config)
            dns_provider.update_record(duckdns_options.hostname or server.name, server.ipv4 or "")
        except Exception as exc:  # pragma: no cover - external failure
            typer.secho(f"Aktualizacja DuckDNS nie powiodła się: {exc}", fg=typer.colors.YELLOW)


def _resolve_server_type(provider, choice: Optional[str]) -> ServerTypeInfo:
    """Return selected server type, optionally via interactive prompt."""

    types = provider.list_server_types()
    if not types:
        typer.secho("Brak dostępnych typów serwerów", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    if choice:
        for item in types:
            if item.identifier == choice:
                return item
        typer.secho(f"Nie znaleziono typu serwera: {choice}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    selection = questionary.select(
        "Wybierz typ serwera",
        choices=[
            questionary.Choice(
                title=f"{it.name} – {it.cores} vCPU / {it.memory_gb}GB RAM / {it.disk_gb}GB SSD / €{it.price_hourly}/h",
                value=it,
            )
            for it in types
        ],
    ).ask()
    if selection is None:
        typer.secho("Nie wybrano typu serwera", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)
    return selection


def _resolve_image(provider, choice: Optional[str]):
    """Return selected image information."""

    images = provider.list_images()
    if not images:
        typer.secho("Brak dostępnych obrazów systemu", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    if choice:
        for item in images:
            if item.identifier == choice:
                return item
        typer.secho(f"Nie znaleziono obrazu: {choice}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    selection = questionary.select(
        "Wybierz obraz systemu",
        choices=[
            questionary.Choice(title=f"{img.name}", value=img) for img in images
        ],
    ).ask()
    if selection is None:
        typer.secho("Nie wybrano obrazu", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)
    return selection


def _ask_duckdns_options(config: AppConfig) -> DuckDNSOptions:
    """Collect DuckDNS related preferences."""

    if not config.duckdns_token:
        return DuckDNSOptions(enabled=False, hostname=None)

    enabled = questionary.confirm("Czy podpiąć DuckDNS?", default=True).ask()
    if not enabled:
        return DuckDNSOptions(enabled=False, hostname=None)
    hostname = questionary.text("Podaj subdomenę DuckDNS:").ask() or None
    return DuckDNSOptions(enabled=True, hostname=hostname)


def _ask_cloud_init_options() -> CloudInitOptions:
    """Prompt user for optional cloud-init script information."""

    enabled = questionary.confirm("Czy dodać cloud-init script?", default=False).ask()
    if not enabled:
        return CloudInitOptions(enabled=False, path=None, runtime=None, content=None)

    runtime = questionary.select(
        "Wybierz rodzaj skryptu",
        choices=[questionary.Choice("shell"), questionary.Choice("python")],
    ).ask()
    path_str = questionary.path("Podaj ścieżkę do skryptu").ask()
    if not path_str:
        return CloudInitOptions(enabled=False, path=None, runtime=None, content=None)
    path = Path(path_str).expanduser()
    if not path.exists():
        typer.secho(f"Plik {path} nie istnieje", fg=typer.colors.RED)
        return CloudInitOptions(enabled=False, path=None, runtime=None, content=None)

    content = path.read_text(encoding="utf-8")
    if runtime == "python":
        header = "#!/usr/bin/env python3\n"
    else:
        header = "#!/bin/bash\n"
    cloud_init_script = f"{header}{content}"
    return CloudInitOptions(enabled=True, path=path, runtime=runtime, content=cloud_init_script)


def _build_summary_table(
    name: str,
    project: str,
    server_type: ServerTypeInfo,
    image,
    duckdns: DuckDNSOptions,
    cloud_init: CloudInitOptions,
) -> Table:
    """Return summary table for final confirmation."""

    table = Table(show_header=False)
    table.add_column("Klucz", style="bold")
    table.add_column("Wartość")

    table.add_row("Nazwa serwera", name)
    table.add_row("Projekt", project)
    table.add_row(
        "Typ serwera",
        f"{server_type.name} ({server_type.cores} vCPU / {server_type.memory_gb}GB RAM / €{server_type.price_hourly}/h)",
    )
    table.add_row("Obraz", image.name)
    table.add_row(
        "DuckDNS",
        "Brak" if not duckdns.enabled else f"Tak – {duckdns.hostname or 'bez nazwy'}",
    )
    table.add_row(
        "Cloud-init",
        "Brak" if not cloud_init.enabled else f"Tak – {cloud_init.runtime} ({cloud_init.path})",
    )
    return table
