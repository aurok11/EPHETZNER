"""Tests for the Paramiko-based SSH service."""

from __future__ import annotations

import io
import types
import unittest
from typing import List
from unittest.mock import patch

from services.ssh import ParamikoSSHService


class _Stream:
    def __init__(self, *, data: str = "", exit_status: int = 0) -> None:
        self._data = data
        self._buffer = io.BytesIO(data.encode("utf-8"))
        self.channel = types.SimpleNamespace(recv_exit_status=lambda: exit_status)

    def read(self) -> bytes:
        return self._buffer.read()

    def close(self) -> None:  # pragma: no cover - close is a no-op in fakes
        return None


class _FakeSFTPClient:
    def __init__(self) -> None:
        self.put_calls: List[tuple[str, str]] = []
        self.get_calls: List[tuple[str, str]] = []

    def put(self, local_path: str, remote_path: str) -> None:
        self.put_calls.append((local_path, remote_path))

    def get(self, remote_path: str, local_path: str) -> None:
        self.get_calls.append((remote_path, local_path))

    def close(self) -> None:  # pragma: no cover - close is a no-op in fakes
        return None


class _FakeSSHClient:
    def __init__(self, *, command_exit: int = 0, stdout: str = "output", stderr: str = "") -> None:
        self.command_exit = command_exit
        self.stdout = stdout
        self.stderr = stderr
        self.exec_calls: List[str] = []
        self.connected_kwargs: dict | None = None
        self.sftp = _FakeSFTPClient()

    def set_missing_host_key_policy(self, _policy: object) -> None:  # pragma: no cover - unused
        return None

    def connect(self, **kwargs):
        self.connected_kwargs = kwargs

    def exec_command(self, command: str, timeout: int = 60):
        self.exec_calls.append(command)
        return (
            _Stream(),
            _Stream(data=self.stdout, exit_status=self.command_exit),
            _Stream(data=self.stderr, exit_status=self.command_exit),
        )

    def open_sftp(self) -> _FakeSFTPClient:
        return self.sftp

    def close(self) -> None:  # pragma: no cover - close is a no-op in fakes
        return None


class ParamikoSSHServiceTests(unittest.TestCase):
    """Ensure ParamikoSSHService delegates to the client correctly."""

    def setUp(self) -> None:
        self.service = ParamikoSSHService(username="root", key_path=None, password=None)

    def test_run_returns_stdout(self) -> None:
        fake_client = _FakeSSHClient(stdout="hello", command_exit=0)
        with patch("services.ssh.paramiko.SSHClient", return_value=fake_client):
            output = self.service.run("example", ["echo", "hello"])
        self.assertEqual(output, "hello")
        self.assertIn("echo", fake_client.exec_calls[0])

    def test_run_raises_on_failure(self) -> None:
        fake_client = _FakeSSHClient(stdout="", stderr="boom", command_exit=1)
        with patch("services.ssh.paramiko.SSHClient", return_value=fake_client):
            with self.assertRaises(RuntimeError):
                self.service.run("example", ["false"])

    def test_upload_calls_put(self) -> None:
        fake_client = _FakeSSHClient()
        with patch("services.ssh.paramiko.SSHClient", return_value=fake_client):
            self.service.upload("example", "local.txt", "remote.txt")
        self.assertEqual(fake_client.sftp.put_calls, [("local.txt", "remote.txt")])

    def test_download_calls_get(self) -> None:
        fake_client = _FakeSSHClient()
        with patch("services.ssh.paramiko.SSHClient", return_value=fake_client):
            self.service.download("example", "remote.txt", "local.txt")
        self.assertEqual(fake_client.sftp.get_calls, [("remote.txt", "local.txt")])


if __name__ == "__main__":  # pragma: no cover - convenience
    unittest.main()
