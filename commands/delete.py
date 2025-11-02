"""Typer command responsible for deleting ephemeral servers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import questionary
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ephetzner_core import AppConfig, resolve_config
from ephetzner_core.localization import _
from services.base import BackupProvider, CloudProvider, BackupRequest, BackupResult, ServerInstance
from services.providers import build_backup_provider, build_cloud_provider

EPHEMERAL_LABEL = {"Type": "Ephemeral"}


@dataclass(slots=True)
class BackupOptions:
    """Metadata describing the optional backup requested by the user."""

    enabled: bool
    remote_path: Optional[str]
    destination_prefix: Optional[str]


def register(app_root: typer.Typer) -> None:
    """Register the delete command with the Typer application."""

    app_root.command("delete")(delete)


def delete(
    server_id: Optional[str] = typer.Option(None, "--server-id", help="Server identifier to delete"),
    skip_backup: bool = typer.Option(False, "--skip-backup", help="Skip backup even if configured"),
) -> None:
    """Delete an ephemeral server with optional backup."""

    console = Console()
    config = resolve_config()
    provider = build_cloud_provider(config)

    server = _select_server(provider, server_id)
    backup_opts = _collect_backup_preferences(config, skip_backup)

    summary_table = _build_summary(server, backup_opts)
    console.print(Panel(summary_table, title=_("Deletion confirmation")))

    if not questionary.confirm(_("Continue?"), default=True).ask():
        typer.secho(_("Operation cancelled"), fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)

    if backup_opts.enabled:
        backup_provider = build_backup_provider(config)
        backup_success, _ = _perform_backup(backup_provider, server, backup_opts, console)
        if not backup_success:
            typer.secho(_("Backup failed"), fg=typer.colors.RED)
            raise typer.Exit(code=1)

    try:
        provider.delete_server(server.identifier)
    except NotImplementedError:
        typer.secho(
            _("Server deletion is not implemented yet."),
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=1)
    except Exception as exc:  # pragma: no cover - defensive guard
        typer.secho(
            _("Server deletion failed: {error}").format(error=exc),
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    console.print(
        _("[green]Server {name} ({identifier}) deleted successfully.[/green]").format(
            name=server.name,
            identifier=server.identifier,
        )
    )


def _select_server(provider: CloudProvider, server_id: Optional[str]) -> ServerInstance:
    """Return server selected interactively or via option."""

    try:
        servers = provider.list_servers(labels=EPHEMERAL_LABEL)
    except NotImplementedError:
        typer.secho(
            _("Server listing is not implemented yet."),
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=1)
    except Exception as exc:  # pragma: no cover - defensive guard
        typer.secho(
            _("Failed to fetch server list: {error}").format(error=exc),
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)
    if not servers:
        typer.secho(_("No servers labeled as Ephemeral"), fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)

    if server_id:
        for server in servers:
            if server.identifier == server_id:
                return server
        typer.secho(
            _("Server {identifier} not found").format(identifier=server_id),
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    choice = questionary.select(
        _("Select server to delete"),
        choices=[
            questionary.Choice(
                title=f"{srv.name} ({srv.server_type}) – {srv.ipv4 or _('no IPv4')}",
                value=srv,
            )
            for srv in servers
        ],
    ).ask()
    if choice is None:
        typer.secho(_("No server selected"), fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)
    return choice


def _collect_backup_preferences(config: AppConfig, skip_backup: bool) -> BackupOptions:
    """Prompt user for backup configuration if enabled."""

    if skip_backup:
        return BackupOptions(enabled=False, remote_path=None, destination_prefix=None)

    if not (config.s3_access_key and config.s3_secret_key):
        typer.secho(
            _("S3 configuration incomplete – skipping backup."),
            fg=typer.colors.YELLOW,
        )
        return BackupOptions(enabled=False, remote_path=None, destination_prefix=None)

    enabled_answer = questionary.confirm(_("Perform S3 backup?"), default=True).ask()
    if not enabled_answer:
        return BackupOptions(enabled=False, remote_path=None, destination_prefix=None)

    remote_path = questionary.text(
        _("Provide remote backup path"),
        default="/var/backups",
    ).ask()
    destination = questionary.text(
        _("Provide S3 destination prefix (e.g. s3://bucket/path)"),
        default="",
    ).ask()
    return BackupOptions(
        enabled=True,
        remote_path=remote_path or "/var/backups",
        destination_prefix=destination or "",
    )


def _build_summary(server: ServerInstance, backup: BackupOptions) -> Table:
    """Build a Rich table summarising delete operation."""

    now = datetime.now(timezone.utc)
    created_at = server.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age = now - created_at
    hours = round(age.total_seconds() / 3600, 2)

    table = Table(show_header=False)
    table.add_column(_("Field"), style="bold")
    table.add_column(_("Value"))
    table.add_row(_("Server"), f"{server.name} ({server.identifier})")
    table.add_row(_("Type"), server.server_type)
    table.add_row(_("IPv4 address"), server.ipv4 or _("none"))
    table.add_row(_("Uptime"), f"~{hours} h")
    table.add_row(
        _("Backup"),
        _("None")
        if not backup.enabled
        else f"{backup.remote_path} -> {backup.destination_prefix}",
    )
    return table


def _perform_backup(
    backup_provider: BackupProvider,
    server: ServerInstance,
    backup: BackupOptions,
    console: Console,
) -> tuple[bool, Optional[BackupResult]]:
    """Execute backup procedure prior to deletion.

    Returns a tuple of (success flag, optional result). ``True`` indicates the
    deletion flow may proceed. ``False`` signals that the backup failed and the
    command should abort.
    """

    console.print(_("[blue]Starting backup...[/blue]"))
    request = BackupRequest(
        server=server,
        remote_path=backup.remote_path or "/",
        archive_name=f"{server.name}-backup.tar.gz",
        destination_prefix=backup.destination_prefix or "",
    )
    try:
        result = backup_provider.create_backup(request)
        if not backup_provider.verify_backup(result):
            console.print(_("[red]Backup verification failed[/red]"))
            return False, None
        console.print(
            _("[green]Backup finished: {location}[/green]").format(
                location=result.location,
            )
        )
        return True, result
    except NotImplementedError:
        console.print(_("[yellow]Backup functionality is not available yet.[/yellow]"))
        return True, None
    except Exception as exc:  # pragma: no cover - defensive guard
        console.print(
            _("[red]Backup error: {error}[/red]").format(error=exc)
        )
        return False, None
