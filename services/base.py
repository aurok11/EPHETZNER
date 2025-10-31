"""Abstract base classes defining high-level service contracts.

These ABCs make it easy to plug alternative cloud or DNS providers without
modifying the CLI logic. Concrete implementations should live in dedicated
modules (for example ``services.hetzner``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Sequence


@dataclass(slots=True)
class ServerTypeInfo:
    """Describes a VM flavor offered by the infrastructure provider."""

    identifier: str
    name: str
    cores: int
    memory_gb: float
    disk_gb: int
    price_hourly: float


@dataclass(slots=True)
class ImageInfo:
    """Represents an operating system image available for provisioning."""

    identifier: str
    name: str
    description: str | None = None


@dataclass(slots=True)
class ServerInstance:
    """Metadata describing a running or provisioned server instance."""

    identifier: str
    name: str
    server_type: str
    image: str
    ipv4: str | None
    ipv6: str | None
    created_at: datetime
    labels: Mapping[str, str]


@dataclass(slots=True)
class ProvisioningRequest:
    """Input parameters required to create an ephemeral workspace."""

    name: str
    server_type: str
    image: str
    labels: Mapping[str, str]
    project: str | None = None
    cloud_init: str | None = None


@dataclass(slots=True)
class BackupRequest:
    """Request describing which data should be archived before deletion."""

    server: ServerInstance
    remote_path: str
    archive_name: str
    destination_prefix: str


@dataclass(slots=True)
class BackupResult:
    """Information produced after a backup succeeds."""

    location: str
    checksum: str
    size_bytes: int


class CloudProvider(ABC):
    """Operations required from any infrastructure provider."""

    @abstractmethod
    def list_server_types(self, *, refresh: bool = False) -> Sequence[ServerTypeInfo]:
        """Return server flavors available for provisioning."""

    @abstractmethod
    def list_images(self, *, refresh: bool = False) -> Sequence[ImageInfo]:
        """Return a list of OS images available to the account."""

    @abstractmethod
    def list_servers(self, *, labels: Mapping[str, str] | None = None) -> Sequence[ServerInstance]:
        """Return servers matching optional label selector."""

    @abstractmethod
    def create_server(self, request: ProvisioningRequest) -> ServerInstance:
        """Provision a new server matching the request."""

    @abstractmethod
    def assign_labels(self, server_id: str, labels: Mapping[str, str]) -> None:
        """Attach labels/metadata to a server."""

    @abstractmethod
    def delete_server(self, server_id: str) -> None:
        """Destroy a previously provisioned server."""

    @abstractmethod
    def get_server(self, server_id: str) -> ServerInstance:
        """Fetch metadata about an existing server."""


class DNSProvider(ABC):
    """Interface describing dynamic DNS operations."""

    @abstractmethod
    def update_record(self, host: str, ipv4: str, *, ttl: int = 60) -> None:
        """Set host to the given IPv4 address with optional TTL."""


class BackupProvider(ABC):
    """Contract for creating and verifying backups."""

    @abstractmethod
    def create_backup(self, request: BackupRequest) -> BackupResult:
        """Produce archive from remote path and upload to destination."""

    @abstractmethod
    def verify_backup(self, result: BackupResult) -> bool:
        """Validate checksum or existence of the produced backup."""


class SSHService(ABC):
    """Abstraction for executing commands on remote servers via SSH."""

    @abstractmethod
    def run(self, host: str, command: Sequence[str], *, timeout: int = 60) -> str:
        """Execute a command on the remote host and return stdout."""

    @abstractmethod
    def upload(self, host: str, local_path: str, remote_path: str) -> None:
        """Upload a local file to the remote host."""

    @abstractmethod
    def download(self, host: str, remote_path: str, local_path: str) -> None:
        """Download a file from the remote host."""
