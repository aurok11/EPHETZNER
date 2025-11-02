"""Implementation scaffold for Hetzner Cloud provider."""

from __future__ import annotations

import base64
import binascii
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from hcloud import Client
from hcloud.exceptions import APIException

from services.base import (
    CloudProvider,
    ImageInfo,
    ProvisioningRequest,
    SSHKeyInfo,
    ServerInstance,
    ServerTypeInfo,
)


logger = logging.getLogger(__name__)


def _compute_ssh_fingerprint(public_key: str) -> str:
    """Compute a short identifier for an SSH key from base64-decoded key material.
    
    This returns the first 12 characters of the MD5 hash of the decoded public key material.
    The result is a shortened identifier for internal use and is not a standard SSH fingerprint.
    Do not use for cryptographic security or interoperability with SSH tooling expecting standard fingerprints.
    
    Args:
        public_key: SSH public key in OpenSSH format (e.g., "ssh-rsa AAAA... comment")
    
    Returns:
        Short hex fingerprint suitable for key identification (first 12 chars of MD5 hash)
    """
    parts = public_key.strip().split()
    if len(parts) < 2:
        # Fallback for malformed keys
        return hashlib.md5(public_key.encode("utf-8")).hexdigest()[:12]
    
    key_data = parts[1]
    try:
        # Decode the base64 key material
        decoded = base64.b64decode(key_data)
        # Calculate MD5 fingerprint of the decoded key material
        return hashlib.md5(decoded).hexdigest()[:12]
    except (binascii.Error, ValueError):
        # Fallback if base64 decoding fails
        return hashlib.md5(public_key.encode("utf-8")).hexdigest()[:12]


_SAMPLE_SERVER_TYPES: tuple[ServerTypeInfo, ...] = (
    ServerTypeInfo("cx21", "cx21", cores=2, memory_gb=4.0, disk_gb=40, price_hourly=0.006),
    ServerTypeInfo("cx31", "cx31", cores=4, memory_gb=8.0, disk_gb=80, price_hourly=0.010),
)

_SAMPLE_IMAGES: tuple[ImageInfo, ...] = (
    ImageInfo("ubuntu-22.04", "Ubuntu 22.04"),
    ImageInfo("debian-12", "Debian 12"),
)

_SAMPLE_INSTANCE = ServerInstance(
    identifier="sample-1",
    name="ephemeral-sample",
    server_type="cx21",
    image="ubuntu-22.04",
    ipv4="203.0.113.10",
    ipv6=None,
    created_at=datetime.now(timezone.utc),
    labels={"Type": "Ephemeral"},
)


class HetznerCloudProvider(CloudProvider):
    """Hetzner Cloud implementation of ``CloudProvider`` contract."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def _require_client(self) -> Client:
        if not self._client:
            raise RuntimeError("Hetzner API client is not configured")
        return self._client

    def _convert_server(self, server: Any) -> ServerInstance:
        created = getattr(server, "created", None)
        if isinstance(created, str):
            created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        elif isinstance(created, datetime):
            created_dt = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
        else:
            created_dt = datetime.now(timezone.utc)

        public_net = getattr(server, "public_net", None)
        ipv4 = None
        ipv6 = None
        if public_net:
            if getattr(public_net, "ipv4", None):
                ipv4 = getattr(public_net.ipv4, "ip", None)
            if getattr(public_net, "ipv6", None):
                ipv6 = getattr(public_net.ipv6, "ip", None)

        server_type = getattr(server, "server_type", None)
        server_type_name = getattr(server_type, "name", None) or getattr(server_type, "id", "unknown")

        image = getattr(server, "image", None)
        image_name = getattr(image, "description", None) or getattr(image, "name", None) or "unknown"

        labels = getattr(server, "labels", {}) or {}

        return ServerInstance(
            identifier=str(getattr(server, "id", "unknown")),
            name=getattr(server, "name", "unknown"),
            server_type=str(server_type_name),
            image=str(image_name),
            ipv4=ipv4,
            ipv6=ipv6,
            created_at=created_dt,
            labels=labels,
        )

    def list_server_types(self, *, refresh: bool = False) -> Sequence[ServerTypeInfo]:
        logger.debug("Fetching server types from Hetzner", extra={"refresh": refresh})
        if not self._client:
            return list(_SAMPLE_SERVER_TYPES)
        try:
            server_types = self._client.server_types.get_all()
        except Exception as exc:  # pragma: no cover - network failure fallback
            logger.warning("Falling back to sample server types", exc_info=exc)
            return list(_SAMPLE_SERVER_TYPES)
        result: list[ServerTypeInfo] = []
        for st in server_types:
            prices = getattr(st, "prices", []) or []
            price_hourly = 0.0
            if prices:
                hourly = getattr(prices[0], "price_hourly", None)
                if hourly is None:
                    price_hourly = 0.0
                else:
                    # ``hourly`` can be a simple float or an object with ``net`` attribute.
                    net = getattr(hourly, "net", hourly)
                    try:
                        price_hourly = float(net)
                    except (TypeError, ValueError):
                        price_hourly = 0.0
            result.append(
                ServerTypeInfo(
                    identifier=str(st.id),
                    name=st.name,
                    cores=st.cores,
                    memory_gb=float(getattr(st, "memory", 0)),
                    disk_gb=int(getattr(st, "disk", 0)),
                    price_hourly=price_hourly,
                )
            )
        return result

    def list_images(self, *, refresh: bool = False) -> Sequence[ImageInfo]:
        logger.debug("Fetching images from Hetzner", extra={"refresh": refresh})
        if not self._client:
            return list(_SAMPLE_IMAGES)
        try:
            images = self._client.images.get_all(type="system")
        except Exception as exc:  # pragma: no cover - network failure fallback
            logger.warning("Falling back to sample images", exc_info=exc)
            return list(_SAMPLE_IMAGES)
        return [
            ImageInfo(
                identifier=str(img.id),
                name=img.name or str(img.id),
                description=img.description,
            )
            for img in images
        ]

    def list_servers(self, *, labels: Mapping[str, str] | None = None) -> Sequence[ServerInstance]:
        logger.debug("Listing servers", extra={"labels": labels})
        if not self._client:
            return [_SAMPLE_INSTANCE]
        try:
            servers = self._client.servers.get_all()
        except Exception as exc:  # pragma: no cover - network failure fallback
            logger.warning("Falling back to sample servers", exc_info=exc)
            return [_SAMPLE_INSTANCE]

        result: list[ServerInstance] = []
        for srv in servers:
            srv_labels = srv.labels or {}
            if labels and not all(srv_labels.get(k) == v for k, v in labels.items()):
                continue
            created = getattr(srv, "created", None)
            if isinstance(created, str):
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            else:
                created_dt = created or datetime.now(timezone.utc)
            result.append(
                ServerInstance(
                    identifier=str(srv.id),
                    name=srv.name,
                    server_type=srv.server_type.name if srv.server_type else "unknown",
                    image=srv.image.description if srv.image else "unknown",
                    ipv4=srv.public_net.ipv4.ip if srv.public_net and srv.public_net.ipv4 else None,
                    ipv6=srv.public_net.ipv6.ip if srv.public_net and srv.public_net.ipv6 else None,
                    created_at=created_dt,
                    labels=srv_labels,
                )
            )
        return result

    def list_ssh_keys(self) -> Sequence[SSHKeyInfo]:
        logger.debug("Listing SSH keys from Hetzner")
        client = self._client
        key_api = getattr(client, "ssh_keys", None) if client else None
        if key_api is None:
            return []
        try:
            keys = key_api.get_all()
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("Failed to list Hetzner SSH keys", exc_info=exc)
            return []

        result: list[SSHKeyInfo] = []
        for key in keys:
            fingerprint = getattr(key, "fingerprint", None)
            result.append(
                SSHKeyInfo(
                    identifier=str(getattr(key, "id", getattr(key, "name", "unknown"))),
                    name=getattr(key, "name", "unknown"),
                    fingerprint=str(fingerprint) if fingerprint else None,
                    public_key=getattr(key, "public_key", None),
                )
            )
        return result

    def create_server(self, request: ProvisioningRequest) -> ServerInstance:
        logger.info("Creating server via Hetzner", extra={"request": request})
        client = self._require_client()
        labels = dict(request.labels)
        ssh_keys_param = None
        attempted_key_registration = bool(request.ssh_public_key and request.ssh_public_key.strip())
        if attempted_key_registration:
            ssh_key = self._ensure_ssh_key(request.ssh_public_key, request.name)
            if ssh_key is not None:
                ssh_keys_param = [ssh_key]
        create_kwargs = {
            "name": request.name,
            "server_type": request.server_type,
            "image": request.image,
            "labels": labels,
            "user_data": request.cloud_init,
        }
        if ssh_keys_param is not None:
            create_kwargs["ssh_keys"] = ssh_keys_param

        try:
            response = client.servers.create(**create_kwargs)
            server = getattr(response, "server", None)
            if server is None:
                raise RuntimeError("Hetzner did not return server details")
            return self._convert_server(server)
        except APIException as exc:
            logger.error("Hetzner API error during server creation", exc_info=exc)
            raise RuntimeError(f"Failed to create server: {exc.message}") from exc
        except Exception as exc:  # pragma: no cover - defensive catch
            logger.exception("Unexpected error during server creation")
            raise RuntimeError("Failed to create server") from exc
        finally:
            if attempted_key_registration and ssh_keys_param is None:
                logger.warning(
                    "SSH public key could not be registered with Hetzner API",
                    extra={"server": request.name},
                )

    def assign_labels(self, server_id: str, labels: Mapping[str, str]) -> None:
        logger.debug("Assigning labels", extra={"server_id": server_id, "labels": labels})
        client = self._require_client()
        server = self._get_server_resource(server_id)
        try:
            client.servers.update(server, labels=dict(labels))
        except APIException as exc:
            logger.error("Hetzner API error during label assignment", exc_info=exc)
            raise RuntimeError(f"Failed to assign labels: {exc.message}") from exc
        except Exception as exc:  # pragma: no cover - defensive catch
            logger.exception("Unexpected error assigning labels")
            raise RuntimeError("Failed to assign labels") from exc

    def delete_server(self, server_id: str) -> None:
        logger.info("Deleting server via Hetzner", extra={"server_id": server_id})
        client = self._require_client()
        server = self._get_server_resource(server_id)
        try:
            client.servers.delete(server)
        except APIException as exc:
            logger.error("Hetzner API error during deletion", exc_info=exc)
            raise RuntimeError(f"Failed to delete server: {exc.message}") from exc
        except Exception as exc:  # pragma: no cover - defensive catch
            logger.exception("Unexpected error during server deletion")
            raise RuntimeError("Failed to delete server") from exc

    def get_server(self, server_id: str) -> ServerInstance:
        logger.debug("Fetching server metadata", extra={"server_id": server_id})
        server = self._get_server_resource(server_id)
        return self._convert_server(server)

    def _ensure_ssh_key(self, public_key: str, server_name: str) -> Any | None:
        """Ensure the supplied public key exists in Hetzner and return its handle."""

        client = self._require_client()
        normalized = public_key.strip()
        if not normalized:
            return None

        key_api = getattr(client, "ssh_keys", None)
        if key_api is None:
            logger.warning("Hetzner client does not expose SSH key API")
            return None

        try:
            keys = key_api.get_all()
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("Failed to list Hetzner SSH keys", exc_info=exc)
            keys = []

        for key in keys:
            stored = getattr(key, "public_key", None)
            if stored and stored.strip() == normalized:
                return key

        fingerprint = _compute_ssh_fingerprint(normalized)
        key_name = f"ephetzner-{server_name}-{fingerprint}"[:64]

        try:
            creation = key_api.create(name=key_name, public_key=normalized)
        except APIException as exc:
            logger.error("Hetzner API error during SSH key registration", exc_info=exc)
            message = (exc.message or "").lower()
            if "already exists" in message:
                try:
                    existing = key_api.get_by_name(key_name)
                except Exception:  # pragma: no cover - defensive fallback
                    existing = None
                if existing:
                    return existing
                for key in keys:
                    stored = getattr(key, "public_key", None)
                    if stored and stored.strip() == normalized:
                        return key
                return None
            raise RuntimeError(f"Failed to register SSH key: {exc.message}") from exc
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("Unexpected error registering SSH key", exc_info=exc)
            return None

        ssh_key = getattr(creation, "ssh_key", None)
        return ssh_key or creation

    def _get_server_resource(self, server_id: str) -> Any:
        client = self._require_client()
        try:
            try:
                numeric_id = int(server_id)
            except (TypeError, ValueError):
                server = client.servers.get_by_name(server_id)
            else:
                server = client.servers.get_by_id(numeric_id)
        except APIException as exc:
            logger.error("Hetzner API error while fetching server", exc_info=exc)
            raise RuntimeError(f"Failed to fetch server {server_id}: {exc.message}") from exc
        except Exception as exc:  # pragma: no cover - defensive catch
            logger.exception("Unexpected error fetching server metadata")
            raise RuntimeError(f"Failed to fetch server {server_id}") from exc

        if server is None:
            raise RuntimeError(f"Server {server_id} not found")
        return server
