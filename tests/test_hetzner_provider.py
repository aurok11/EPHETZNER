"""Unit tests for HetznerCloudProvider operations."""

from __future__ import annotations

import types
import unittest
from datetime import datetime, timezone

from services.base import ProvisioningRequest
from services.hetzner import HetznerCloudProvider


class _FakeServersAPI:
    def __init__(self, server: types.SimpleNamespace) -> None:
        self._server = server
        self.create_calls: list[dict] = []
        self.deleted: list[types.SimpleNamespace] = []
        self.updated: list[tuple[types.SimpleNamespace, dict]] = []

    def create(self, **kwargs) -> types.SimpleNamespace:
        self.create_calls.append(kwargs)
        return types.SimpleNamespace(server=self._server)

    def get_by_id(self, server_id: int) -> types.SimpleNamespace | None:
        if server_id == self._server.id:
            return self._server
        return None

    def get_by_name(self, name: str) -> types.SimpleNamespace | None:
        if name == self._server.name:
            return self._server
        return None

    def delete(self, server: types.SimpleNamespace) -> None:
        self.deleted.append(server)

    def update(self, server: types.SimpleNamespace, labels: dict) -> None:
        self.updated.append((server, labels))


class _FakeClient:
    def __init__(self, server: types.SimpleNamespace) -> None:
        self.servers = _FakeServersAPI(server)


class HetznerProviderTests(unittest.TestCase):
    """Verify that the Hetzner provider integrates with the client API."""

    def setUp(self) -> None:  # noqa: D401 - short lifecycle hook description
        created_at = datetime(2024, 5, 1, 12, 0, tzinfo=timezone.utc)
        public_net = types.SimpleNamespace(
            ipv4=types.SimpleNamespace(ip="198.51.100.10"),
            ipv6=types.SimpleNamespace(ip="2001:db8::1"),
        )
        server_type = types.SimpleNamespace(name="cx21")
        image = types.SimpleNamespace(description="Ubuntu 22.04", name="ubuntu-22")
        self.server = types.SimpleNamespace(
            id=123,
            name="ephemeral-123",
            server_type=server_type,
            image=image,
            public_net=public_net,
            created=created_at,
            labels={"Type": "Ephemeral"},
        )
        self.client = _FakeClient(self.server)
        self.provider = HetznerCloudProvider(self.client)

    def test_create_server_returns_instance(self) -> None:
        request = ProvisioningRequest(
            name="ephemeral-123",
            project="sandbox",
            server_type="cx21",
            image="ubuntu-22",
            labels={"Type": "Ephemeral"},
            cloud_init="#cloud-config",
        )

        result = self.provider.create_server(request)

        self.assertEqual(result.identifier, "123")
        self.assertEqual(result.server_type, "cx21")
        self.assertEqual(result.image, "Ubuntu 22.04")
        self.assertEqual(self.client.servers.create_calls[0]["labels"], {"Type": "Ephemeral"})

    def test_delete_server_invokes_client_delete(self) -> None:
        self.provider.delete_server("123")

        self.assertEqual(len(self.client.servers.deleted), 1)
        deleted = self.client.servers.deleted[0]
        self.assertEqual(deleted.id, 123)

    def test_assign_labels_updates_server(self) -> None:
        self.provider.assign_labels("123", {"Type": "Ephemeral", "Owner": "ci"})

        self.assertEqual(len(self.client.servers.updated), 1)
        _, labels = self.client.servers.updated[0]
        self.assertEqual(labels["Owner"], "ci")

    def test_get_server_returns_converted_instance(self) -> None:
        instance = self.provider.get_server("123")

        self.assertEqual(instance.name, "ephemeral-123")
        self.assertEqual(instance.ipv4, "198.51.100.10")
        self.assertEqual(instance.labels["Type"], "Ephemeral")


if __name__ == "__main__":  # pragma: no cover - convenience
    unittest.main()
