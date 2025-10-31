"""S3-compatible backup service implementation."""

from __future__ import annotations

import logging
import os
from contextlib import suppress
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional, Tuple
from urllib.parse import urlparse

import paramiko
from botocore.exceptions import ClientError

import boto3

from services.base import BackupProvider, BackupRequest, BackupResult


logger = logging.getLogger(__name__)


class S3BackupService(BackupProvider):
    """Upload archives to an S3-compatible object storage."""

    def __init__(
        self,
        endpoint_url: Optional[str],
        access_key: Optional[str],
        secret_key: Optional[str],
        *,
        session: Optional[boto3.session.Session] = None,
        ssh_timeout: int = 120,
    ) -> None:
        self._session = session or boto3.session.Session()
        self._endpoint_url = endpoint_url
        self._access_key = access_key
        self._secret_key = secret_key
        self._ssh_timeout = ssh_timeout
        self._client = self._session.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    def create_backup(self, request: BackupRequest) -> BackupResult:
        logger.info(
            "Creating backup archive",
            extra={
                "server": request.server.identifier,
                "remote_path": request.remote_path,
                "destination": request.destination_prefix,
            },
        )
        if not self._access_key or not self._secret_key:
            raise RuntimeError("S3 credentials are not configured")

        if not request.server.ipv4:
            raise RuntimeError("Server IPv4 address is required for backup")

        bucket, key_prefix = self._parse_destination_prefix(request.destination_prefix)
        remote_archive = f"/tmp/{request.archive_name}"

        ssh_client = self._build_ssh_client()
        connect_kwargs = self._build_connect_kwargs(request)

        ssh_client.connect(**connect_kwargs)
        try:
            self._execute_remote_tar(ssh_client, request, remote_archive)

            with TemporaryDirectory(prefix="ephetzner-backup-") as tmp_dir:
                local_archive = Path(tmp_dir) / request.archive_name
                sftp = ssh_client.open_sftp()
                try:
                    sftp.get(remote_archive, str(local_archive))
                finally:
                    with suppress(Exception):
                        sftp.close()

                checksum = self._compute_checksum(local_archive)
                key = self._build_s3_key(key_prefix, request.archive_name)

                self._client.upload_file(str(local_archive), bucket, key)
                size_bytes = local_archive.stat().st_size
        finally:
            with suppress(Exception):
                self._execute_cleanup(ssh_client, remote_archive)
            with suppress(Exception):
                ssh_client.close()

        location = f"s3://{bucket}/{key}"
        return BackupResult(location=location, checksum=checksum, size_bytes=size_bytes)

    def verify_backup(self, result: BackupResult) -> bool:
        logger.debug("Verifying backup", extra={"location": result.location})
        bucket, key = self._parse_backup_location(result.location)
        try:
            response = self._client.get_object(Bucket=bucket, Key=key)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"NoSuchKey", "404"}:
                logger.warning("Backup object missing during verification", extra={"bucket": bucket, "key": key})
                return False
            raise

        body = response["Body"]
        digest = sha256()
        try:
            for chunk in iter(lambda: body.read(1024 * 1024), b""):
                if not chunk:
                    break
                digest.update(chunk)
        finally:
            with suppress(Exception):
                body.close()

        checksum_matches = digest.hexdigest() == result.checksum
        size_matches = response.get("ContentLength") == result.size_bytes
        if not checksum_matches:
            logger.error("Checksum mismatch during backup verification", extra={"expected": result.checksum, "actual": digest.hexdigest()})
        if not size_matches:
            logger.error(
                "Size mismatch during backup verification",
                extra={"expected": result.size_bytes, "actual": response.get("ContentLength")},
            )
        return checksum_matches and size_matches

    def _build_connect_kwargs(self, request: BackupRequest) -> dict:
        labels = request.server.labels or {}
        username = labels.get("ssh_user") or os.getenv("EPHETZNER_SSH_USER", "root")
        key_path = labels.get("ssh_key_path") or os.getenv("EPHETZNER_SSH_KEY_PATH")
        password = os.getenv("EPHETZNER_SSH_PASSWORD")

        kwargs = {
            "hostname": request.server.ipv4,
            "username": username,
            "timeout": self._ssh_timeout,
        }
        if key_path:
            kwargs["key_filename"] = key_path
        if password:
            kwargs["password"] = password
        return kwargs

    def _build_ssh_client(self) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        return client

    def _execute_remote_tar(
        self,
        ssh_client: paramiko.SSHClient,
        request: BackupRequest,
        remote_archive: str,
    ) -> None:
        remote_path = request.remote_path.rstrip("/") or "/"
        command = "sudo tar czf {archive} -C {source} .".format(archive=remote_archive, source=remote_path)
        stdin, stdout, stderr = ssh_client.exec_command(command, timeout=self._ssh_timeout)
        exit_code = stdout.channel.recv_exit_status()
        if exit_code != 0:
            error_output = stderr.read().decode("utf-8", "ignore")
            raise RuntimeError(f"Remote archive command failed ({exit_code}): {error_output}")
        with suppress(Exception):
            stdin.close()
        with suppress(Exception):
            stdout.close()
        with suppress(Exception):
            stderr.close()

    def _execute_cleanup(self, ssh_client: paramiko.SSHClient, remote_archive: str) -> None:
        ssh_client.exec_command(f"rm -f {remote_archive}", timeout=self._ssh_timeout)

    @staticmethod
    def _compute_checksum(local_archive: Path) -> str:
        digest = sha256()
        with local_archive.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _build_s3_key(prefix: str, archive_name: str) -> str:
        if prefix:
            return f"{prefix.rstrip('/')}/{archive_name}"
        return archive_name

    @staticmethod
    def _parse_destination_prefix(prefix: Optional[str]) -> Tuple[str, str]:
        if not prefix:
            raise ValueError("Destination prefix must include the target bucket (e.g. s3://bucket/path)")
        if prefix.startswith("s3://"):
            parsed = urlparse(prefix)
            bucket = parsed.netloc
            key_prefix = parsed.path.lstrip("/")
        else:
            parts = prefix.split("/", 1)
            bucket = parts[0]
            key_prefix = parts[1] if len(parts) > 1 else ""
        if not bucket:
            raise ValueError("S3 bucket name missing in destination prefix")
        return bucket, key_prefix

    @staticmethod
    def _parse_backup_location(location: str) -> Tuple[str, str]:
        parsed = urlparse(location)
        if parsed.scheme != "s3" or not parsed.netloc:
            raise ValueError(f"Unsupported backup location: {location}")
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        if not key:
            raise ValueError(f"Missing object key in backup location: {location}")
        return bucket, key
