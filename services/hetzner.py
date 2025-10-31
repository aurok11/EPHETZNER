"""Implementation scaffold for Hetzner Cloud provider."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from hcloud import Client
from hcloud.exceptions import APIException

from services.base import (
    CloudProvider,
    ImageInfo,
    ProvisioningRequest,
    ServerInstance,
    ServerTypeInfo,
)


logger = logging.getLogger(__name__)

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

    def create_server(self, request: ProvisioningRequest) -> ServerInstance:
        logger.info("Creating server via Hetzner", extra={"request": request})
        client = self._require_client()
        labels = dict(request.labels)
        try:
            response = client.servers.create(
                name=request.name,
                server_type=request.server_type,
                image=request.image,
                labels=labels,
                user_data=request.cloud_init,
            )
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
