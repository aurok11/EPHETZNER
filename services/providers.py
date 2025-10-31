"""Factory helpers for constructing service implementations from configuration."""

from __future__ import annotations

from typing import Optional

from hcloud import Client

from ephetzner_core import AppConfig
from services.base import BackupProvider, CloudProvider, DNSProvider, SSHService
from services.duckdns import DuckDNSProvider
from services.hetzner import HetznerCloudProvider
from services.s3 import S3BackupService
from services.ssh import ParamikoSSHService


def build_cloud_provider(config: AppConfig) -> CloudProvider:
    """Instantiate a cloud provider matching application configuration."""

    client: Optional[Client]
    if config.hetzner_api_token:
        client = Client(token=config.hetzner_api_token)
    else:
        client = None
    return HetznerCloudProvider(client)


def build_dns_provider(config: AppConfig) -> DNSProvider:
    """Return DNS provider implementation based on configuration."""

    if not config.duckdns_token:
        raise ValueError("DuckDNS token not configured")
    return DuckDNSProvider(token=config.duckdns_token)


def build_backup_provider(config: AppConfig) -> BackupProvider:
    """Return S3 compatible backup provider using supplied credentials."""

    return S3BackupService(
        endpoint_url=config.s3_endpoint,
        access_key=config.s3_access_key,
        secret_key=config.s3_secret_key,
    )


def build_ssh_service(username: str, *, key_path: str | None = None, password: str | None = None) -> SSHService:
    """Create default SSH service for remote operations."""

    return ParamikoSSHService(username=username, key_path=key_path, password=password)
