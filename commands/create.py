"""Typer command implementing the interactive server creation flow."""

from __future__ import annotations

import logging
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import questionary
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ephetzner_core import AppConfig, resolve_config
from ephetzner_core.localization import _
from services.base import ProvisioningRequest, SSHKeyInfo, ServerTypeInfo
from services.providers import build_cloud_provider, build_dns_provider
from ui.formatters import config_summary_table

app = typer.Typer(help=_("Create ephemeral Hetzner workspaces"))

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


def _compose_user_data(cloud_init: CloudInitOptions, ssh_public_key: Optional[str]) -> Optional[str]:
    """Combine optional user scripts with authorised key injection."""

    key = (ssh_public_key or "").strip()
    if not key:
        return cloud_init.content

    lines: list[str] = ["#!/bin/bash", "set -euo pipefail", ""]
    lines.extend(
        textwrap.dedent(
            f"""
            mkdir -p /root/.ssh
            chmod 700 /root/.ssh
            cat <<'EOF' >/root/.ssh/authorized_keys
            {key}
            EOF
            chmod 600 /root/.ssh/authorized_keys
            """
        ).strip().splitlines()
    )

    if cloud_init.enabled and cloud_init.content:
        lines.append("")
        if cloud_init.runtime == "python":
            script_lines = cloud_init.content.splitlines()
            lines.extend(
                [
                    "cat <<'PYCODE' >/tmp/ephetzner_user_script.py",
                    *script_lines,
                    "PYCODE",
                    "chmod +x /tmp/ephetzner_user_script.py",
                    "python3 /tmp/ephetzner_user_script.py",
                ]
            )
        else:
            script_lines = cloud_init.content.splitlines()
            if script_lines and script_lines[0].startswith("#!"):
                script_lines = script_lines[1:]
            lines.extend(script_lines)

    combined = "\n".join(line.rstrip() for line in lines if line is not None)
    return combined + "\n"


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

    console.print(Panel(config_summary_table(config), title=_("Configuration overview")))
    provider = build_cloud_provider(config)

    selected_type = _resolve_server_type(provider, server_type)
    selected_image = _resolve_image(provider, image)
    ssh_public_key, ssh_summary = _resolve_ssh_key(config, provider, non_interactive)
    server_name = name or questionary.text(_("Provide server name:")).ask()
    if not server_name:
        typer.secho(_("Server name is required"), fg=typer.colors.RED)
        raise typer.Exit(code=1)

    project_id = project or None

    duckdns_options = _ask_duckdns_options(config)
    cloud_init_options = _ask_cloud_init_options()

    summary = _build_summary_table(
        server_name,
        project_id,
        selected_type,
        selected_image,
        duckdns_options,
        cloud_init_options,
        ssh_summary,
    )
    console.print(Panel(summary, title=_("Operation summary")))

    confirm = questionary.confirm(_("Provision server?"), default=True).ask()
    if not confirm:
        typer.secho(_("Operation cancelled by user"), fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)

    user_data = _compose_user_data(cloud_init_options, ssh_public_key)

    request = ProvisioningRequest(
        name=server_name,
        server_type=selected_type.identifier,
        image=selected_image.identifier,
        labels=_compose_labels(project_id),
        project=project_id,
        cloud_init=user_data,
        ssh_public_key=ssh_public_key,
    )

    try:
        server = provider.create_server(request)
    except NotImplementedError:
        typer.secho(
            _("Server provisioning is not implemented yet. Check the roadmap."),
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=1)
    except Exception as exc:  # pragma: no cover - defensive guard
        typer.secho(
            _("Server creation failed: {error}").format(error=exc),
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    console.print(
        _("[green]Server created successfully: {name} ({identifier})[/green]").format(
            name=server.name,
            identifier=server.identifier,
        )
    )

    if duckdns_options.enabled:
        try:
            dns_provider = build_dns_provider(config)
            dns_provider.update_record(duckdns_options.hostname or server.name, server.ipv4 or "")
        except Exception as exc:  # pragma: no cover - external failure
            typer.secho(
                _("DuckDNS update failed: {error}").format(error=exc),
                fg=typer.colors.YELLOW,
            )


def _resolve_server_type(provider, choice: Optional[str]) -> ServerTypeInfo:
    """Return selected server type, optionally via interactive prompt."""

    types = provider.list_server_types()
    if not types:
        typer.secho(_("No server types available"), fg=typer.colors.RED)
        raise typer.Exit(code=1)

    if choice:
        for item in types:
            if item.identifier == choice:
                return item
        typer.secho(
            _("Server type {value} not found").format(value=choice),
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    selection = questionary.select(
        _("Select server type"),
        choices=[
            questionary.Choice(
                title=f"{it.name} – {it.cores} vCPU / {it.memory_gb}GB RAM / {it.disk_gb}GB SSD / €{it.price_hourly}/h",
                value=it,
            )
            for it in types
        ],
    ).ask()
    if selection is None:
        typer.secho(_("No server type selected"), fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)
    return selection


def _resolve_image(provider, choice: Optional[str]):
    """Return selected image information."""

    images = provider.list_images()
    if not images:
        typer.secho(_("No operating system images available"), fg=typer.colors.RED)
        raise typer.Exit(code=1)

    if choice:
        for item in images:
            if item.identifier == choice:
                return item
        typer.secho(
            _("Image {value} not found").format(value=choice),
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    selection = questionary.select(
        _("Select operating system image"),
        choices=[
            questionary.Choice(title=f"{img.name}", value=img) for img in images
        ],
    ).ask()
    if selection is None:
        typer.secho(_("No image selected"), fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)
    return selection


def _ask_duckdns_options(config: AppConfig) -> DuckDNSOptions:
    """Collect DuckDNS related preferences."""

    if not config.duckdns_token:
        return DuckDNSOptions(enabled=False, hostname=None)

    default_hostname = config.duckdns_subdomain or ""
    enabled = questionary.confirm(_("Configure DuckDNS?"), default=bool(default_hostname)).ask()
    if not enabled:
        return DuckDNSOptions(enabled=False, hostname=None)
    hostname = questionary.text(
        _("Provide DuckDNS subdomain:"),
        default=default_hostname,
    ).ask()
    if not hostname:
        return DuckDNSOptions(enabled=True, hostname=default_hostname or None)
    return DuckDNSOptions(enabled=True, hostname=hostname)


def _ask_cloud_init_options() -> CloudInitOptions:
    """Prompt user for optional cloud-init script information."""

    enabled = questionary.confirm(_("Add a cloud-init script?"), default=False).ask()
    if not enabled:
        return CloudInitOptions(enabled=False, path=None, runtime=None, content=None)

    runtime = questionary.select(
        _("Select script runtime"),
        choices=[questionary.Choice("shell"), questionary.Choice("python")],
    ).ask()
    path_str = questionary.path(_("Provide path to the script")).ask()
    if not path_str:
        return CloudInitOptions(enabled=False, path=None, runtime=None, content=None)
    path = Path(path_str).expanduser()
    if not path.exists():
        typer.secho(
            _("File {path} does not exist").format(path=path),
            fg=typer.colors.RED,
        )
        return CloudInitOptions(enabled=False, path=None, runtime=None, content=None)

    content = path.read_text(encoding="utf-8")
    if runtime == "python":
        header = "#!/usr/bin/env python3\n"
    else:
        header = "#!/bin/bash\n"
    cloud_init_script = f"{header}{content}"
    return CloudInitOptions(enabled=True, path=path, runtime=runtime, content=cloud_init_script)


def _resolve_ssh_key(
    config: AppConfig,
    provider,
    non_interactive: bool,
) -> tuple[Optional[str], str]:
    """Determine which SSH key should be injected into the server."""

    configured_key = (config.ssh_public_key or "").strip() or None
    if non_interactive:
        if configured_key:
            return configured_key, _("Configured key ({hint})").format(hint=_ssh_hint(configured_key))
        return None, _("None")

    try:
        available: Sequence[SSHKeyInfo] = provider.list_ssh_keys()
    except NotImplementedError:
        available = []
    except Exception as exc:  # pragma: no cover - defensive guard
        logging.warning("Failed to list provider SSH keys", exc_info=exc)
        available = []

    choices: list[questionary.Choice] = []
    if configured_key:
        choices.append(
            questionary.Choice(
                title=_("Use configured key ({hint})").format(hint=_ssh_hint(configured_key)),
                value=("configured", configured_key),
            )
        )

    for key in available:
        if not key.public_key:
            continue
        label = _format_hetzner_choice(key)
        choices.append(questionary.Choice(title=label, value=("hetzner", key)))

    choices.append(questionary.Choice(title=_("Paste a new SSH key"), value=("new", None)))
    choices.append(questionary.Choice(title=_("Skip SSH key setup"), value=("skip", None)))

    selection = questionary.select(_("Select SSH key source"), choices=choices).ask()
    if selection is None:
        typer.secho(_("SSH key selection cancelled"), fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)

    action, payload = selection
    if action == "skip":
        return None, _("None")
    if action == "configured":
        assert isinstance(payload, str)
        return payload, _("Configured key ({hint})").format(hint=_ssh_hint(payload))
    if action == "hetzner":
        assert isinstance(payload, SSHKeyInfo)
        public_key = (payload.public_key or "").strip()
        if not public_key:
            typer.secho(_("Selected Hetzner key does not expose a public key"), fg=typer.colors.RED)
            raise typer.Exit(code=1)
        hint = _format_hetzner_summary(payload)
        return public_key, hint

    entered = questionary.text(_("Enter SSH public key"), validate=_validate_public_key).ask()
    if not entered:
        typer.secho(_("SSH public key is required"), fg=typer.colors.RED)
        raise typer.Exit(code=1)
    normalized = entered.strip()
    return normalized, _("New key ({hint})").format(hint=_ssh_hint(normalized))


def _format_hetzner_choice(key: SSHKeyInfo) -> str:
    fingerprint = key.fingerprint or _("no fingerprint")
    return _("Use Hetzner key {name} ({fingerprint})").format(name=key.name, fingerprint=fingerprint)


def _format_hetzner_summary(key: SSHKeyInfo) -> str:
    fingerprint = key.fingerprint or _("no fingerprint")
    return _("Hetzner key {name} ({fingerprint})").format(name=key.name, fingerprint=fingerprint)


def _ssh_hint(public_key: str) -> str:
    parts = public_key.strip().split()
    if len(parts) >= 3:
        return parts[2]
    if len(parts) >= 2:
        prefix = parts[1][:8]
        suffix = parts[1][-8:]
        if len(parts[1]) > 16:
            return f"{prefix}…{suffix}"
        return parts[1]
    return (public_key.strip()[:12] + "…") if len(public_key.strip()) > 12 else public_key.strip()


def _validate_public_key(value: str) -> bool:
    """Validate SSH public key format and content.
    
    Checks that:
    1. Key has the expected structure (type + base64 data [+ optional comment])
    2. Key type is one of the supported types
    3. Base64 data is valid
    """
    import base64
    
    normalized = (value or "").strip()
    if not normalized:
        return False
    
    parts = normalized.split()
    if len(parts) < 2:
        return False
    
    # Valid SSH key types
    valid_key_types = {
        'ssh-rsa',
        'ssh-dss',
        'ssh-ed25519',
        'ecdsa-sha2-nistp256',
        'ecdsa-sha2-nistp384',
        'ecdsa-sha2-nistp521',
        'sk-ecdsa-sha2-nistp256@openssh.com',
        'sk-ssh-ed25519@openssh.com',
    }
    
    key_type = parts[0]
    key_data = parts[1]
    
    # Check if key type is valid
    if key_type not in valid_key_types:
        return False
    
    # Validate that the key data is valid base64
    try:
        base64.b64decode(key_data, validate=True)
    except Exception:
        return False
    
    return True


def _build_summary_table(
    name: str,
    project: Optional[str],
    server_type: ServerTypeInfo,
    image,
    duckdns: DuckDNSOptions,
    cloud_init: CloudInitOptions,
    ssh_summary: str,
) -> Table:
    """Return summary table for final confirmation."""

    table = Table(show_header=False)
    table.add_column(_("Field"), style="bold")
    table.add_column(_("Value"))

    table.add_row(_("Server name"), name)
    project_display = project if project else _("Linked to API token")
    table.add_row(_("Project"), project_display)
    table.add_row(
        _("Server type"),
        f"{server_type.name} ({server_type.cores} vCPU / {server_type.memory_gb}GB RAM / €{server_type.price_hourly}/h)",
    )
    table.add_row(_("Image"), image.name)
    table.add_row(
        _("DuckDNS"),
        _("None")
        if not duckdns.enabled
        else _("Yes – {detail}").format(detail=duckdns.hostname or _("unnamed")),
    )
    table.add_row(
        _("Cloud-init"),
        _("None")
        if not cloud_init.enabled
        else _("Yes – {detail}").format(
            detail=f"{cloud_init.runtime} ({cloud_init.path})",
        ),
    )
    table.add_row(_("SSH key"), ssh_summary)
    return table


def _compose_labels(project: Optional[str]) -> dict[str, str]:
    """Compose default label set for newly provisioned servers."""

    labels = dict(EPHEMERAL_LABEL)
    if project:
        labels["Project"] = project
    return labels
