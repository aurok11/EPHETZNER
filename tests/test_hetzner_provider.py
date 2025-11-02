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


class _FakeSSHKey:
    def __init__(self, name: str, public_key: str, fingerprint: str | None = None) -> None:
        self.name = name
        self.public_key = public_key
        self.fingerprint = fingerprint or "aa:bb:cc"
        self.id = hash((name, public_key)) & 0xFFFF


class _FakeSSHKeysAPI:
    def __init__(self) -> None:
        self._keys: list[_FakeSSHKey] = []
        self.created: list[_FakeSSHKey] = []

    def add(self, name: str, public_key: str) -> _FakeSSHKey:
        key = _FakeSSHKey(name, public_key)
        self._keys.append(key)
        return key

    def get_all(self):
        return list(self._keys)

    def get_by_name(self, name: str):
        for key in self._keys:
            if key.name == name:
                return key
        return None

    def create(self, *, name: str, public_key: str):
        key = _FakeSSHKey(name, public_key)
        self._keys.append(key)
        self.created.append(key)
        return types.SimpleNamespace(ssh_key=key)


class _FakeClient:
    def __init__(self, server: types.SimpleNamespace) -> None:
        self.servers = _FakeServersAPI(server)
        self.ssh_keys = _FakeSSHKeysAPI()


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

    def test_create_server_attaches_existing_ssh_key(self) -> None:
        key_value = "ssh-ed25519 AAAATESTKEY"
        existing = self.client.ssh_keys.add("ephetzner-existing", key_value)

        request = ProvisioningRequest(
            name="ephemeral-ssh",
            project=None,
            server_type="cx31",
            image="ubuntu-22",
            labels={"Type": "Ephemeral"},
            cloud_init=None,
            ssh_public_key=key_value,
        )

        self.provider.create_server(request)

        call_kwargs = self.client.servers.create_calls[-1]
        self.assertIn("ssh_keys", call_kwargs)
        self.assertEqual(call_kwargs["ssh_keys"], [existing])

    def test_create_server_creates_ssh_key_when_missing(self) -> None:
        key_value = "ssh-ed25519 AAAANEWKEY"
        request = ProvisioningRequest(
            name="ephemeral-new",
            project=None,
            server_type="cx21",
            image="ubuntu-22",
            labels={"Type": "Ephemeral"},
            cloud_init=None,
            ssh_public_key=key_value,
        )

        self.provider.create_server(request)

        self.assertEqual(len(self.client.ssh_keys.created), 1)
        created = self.client.ssh_keys.created[0]
        self.assertEqual(created.public_key, key_value)

    def test_list_ssh_keys_returns_metadata(self) -> None:
        key_value = "ssh-ed25519 AAAATESTKEY"
        created = self.client.ssh_keys.add("ephetzner-existing", key_value)

        result = self.provider.list_ssh_keys()

        self.assertEqual(len(result), 1)
        info = result[0]
        self.assertEqual(info.name, created.name)
        self.assertEqual(info.public_key, created.public_key)

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
