"""Unit tests for the S3 backup service."""

from __future__ import annotations

import io
import shutil
import tarfile
import tempfile
import types
import unittest
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple
from unittest.mock import patch

from botocore.exceptions import ClientError

from services.base import BackupRequest, BackupResult, ServerInstance
from services.s3 import S3BackupService


class _FakeS3Client:
    def __init__(self) -> None:
        self.storage: Dict[Tuple[str, str], bytes] = {}

    def upload_file(self, filename: str, bucket: str, key: str) -> None:
        with open(filename, "rb") as handle:
            self.storage[(bucket, key)] = handle.read()

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        try:
            data = self.storage[(Bucket, Key)]
        except KeyError as exc:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject") from exc
        return {
            "Body": io.BytesIO(data),
            "ContentLength": len(data),
        }


class _FakeSession:
    def __init__(self, client: _FakeS3Client) -> None:
        self._client = client

    def client(self, service_name: str, **_: object) -> _FakeS3Client:
        if service_name != "s3":  # pragma: no cover - defensive guard
            raise ValueError(f"Unsupported service {service_name}")
        return self._client


class _Stream:
    def __init__(self, exit_status: int = 0, data: bytes | None = None) -> None:
        self._data = data or b""
        self.channel = types.SimpleNamespace(recv_exit_status=lambda: exit_status)

    def read(self) -> bytes:
        return self._data

    def close(self) -> None:  # pragma: no cover - simple stub
        return None


class _FakeSFTPClient:
    def __init__(self, remote_files: Dict[str, Path]) -> None:
        self._remote_files = remote_files

    def get(self, remote_path: str, local_path: str) -> None:
        shutil.copyfile(self._remote_files[remote_path], local_path)

    def close(self) -> None:  # pragma: no cover - simple stub
        return None


class _FakeSSHClient:
    def __init__(self, remote_payload: bytes) -> None:
        self.remote_payload = remote_payload
        self.remote_files: Dict[str, Path] = {}
        self.commands: list[str] = []
        self._tmp_dirs: list[Path] = []
        self.connected_kwargs: dict | None = None

    def set_missing_host_key_policy(self, _policy: object) -> None:  # pragma: no cover - unused in test
        return None

    def connect(self, **kwargs: object) -> None:
        self.connected_kwargs = kwargs

    def exec_command(self, command: str, timeout: int = 60) -> Tuple[_Stream, _Stream, _Stream]:
        self.commands.append(command)
        if "tar" in command and "czf" in command:
            parts = command.split()
            try:
                index = parts.index("czf")
                archive_path = parts[index + 1]
            except (ValueError, IndexError) as exc:  # pragma: no cover - defensive guard
                raise AssertionError(f"Unexpected tar command: {command}") from exc
            tmp_dir = Path(tempfile.mkdtemp())
            self._tmp_dirs.append(tmp_dir)
            archive_file = tmp_dir / Path(archive_path).name
            with tarfile.open(archive_file, "w:gz") as tar:
                info = tarfile.TarInfo(name="data.txt")
                info.size = len(self.remote_payload)
                tar.addfile(info, io.BytesIO(self.remote_payload))
            self.remote_files[archive_path] = archive_file
        elif command.startswith("rm -f"):
            path = command.split(" ")[-1]
            self.remote_files.pop(path, None)
        return _Stream(), _Stream(), _Stream()

    def open_sftp(self) -> _FakeSFTPClient:
        return _FakeSFTPClient(self.remote_files)

    def close(self) -> None:
        for path in self.remote_files.values():
            with suppress(Exception):
                path.unlink()
        self.remote_files.clear()
        for directory in self._tmp_dirs:
            shutil.rmtree(directory, ignore_errors=True)
        self._tmp_dirs.clear()


class S3BackupServiceTests(unittest.TestCase):
    """Exercise the backup workflow end-to-end using fakes."""

    def setUp(self) -> None:  # noqa: D401 - lifecycle hook
        self.s3_client = _FakeS3Client()
        self.session = _FakeSession(self.s3_client)
        self.ssh_client = _FakeSSHClient(b"backup-data")

        self.server = ServerInstance(
            identifier="srv-1",
            name="srv-1",
            server_type="cx21",
            image="ubuntu",
            ipv4="192.0.2.10",
            ipv6=None,
            created_at=datetime(2024, 5, 1, 12, 0, tzinfo=timezone.utc),
            labels={"ssh_user": "root"},
        )
        self.request = BackupRequest(
            server=self.server,
            remote_path="/var/data",
            archive_name="srv-1-backup.tar.gz",
            destination_prefix="s3://bucket/backups",
        )

    def test_create_backup_uploads_object(self) -> None:
        with patch("services.s3.paramiko.SSHClient", side_effect=lambda: self.ssh_client), patch(
            "services.s3.paramiko.AutoAddPolicy",
            return_value=types.SimpleNamespace(),
        ):
            service = S3BackupService(
                endpoint_url=None,
                access_key="key",
                secret_key="secret",
                session=self.session,
            )
            result = service.create_backup(self.request)

        self.assertTrue(result.size_bytes > 0)
        self.assertTrue(result.location.endswith(self.request.archive_name))
        self.assertIn(("bucket", "backups/" + self.request.archive_name), self.s3_client.storage)

        # Verify checksum and size.
        self.assertTrue(service.verify_backup(result))

    def test_verify_backup_returns_false_when_object_missing(self) -> None:
        with patch("services.s3.paramiko.SSHClient", side_effect=lambda: self.ssh_client), patch(
            "services.s3.paramiko.AutoAddPolicy",
            return_value=types.SimpleNamespace(),
        ):
            service = S3BackupService(
                endpoint_url=None,
                access_key="key",
                secret_key="secret",
                session=self.session,
            )

        missing = BackupResult(
            location="s3://bucket/backups/missing.tar.gz",
            checksum="deadbeef",
            size_bytes=123,
        )
        self.assertFalse(service.verify_backup(missing))


if __name__ == "__main__":  # pragma: no cover - convenience entrypoint
    unittest.main()
