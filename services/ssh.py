"""SSH utilities scaffold built on top of Paramiko."""

from __future__ import annotations

import logging
import shlex
from contextlib import suppress
from typing import Sequence

import paramiko

from services.base import SSHService


logger = logging.getLogger(__name__)


class ParamikoSSHService(SSHService):
    """Default SSH implementation using Paramiko transport."""

    def __init__(self, *, username: str, key_path: str | None = None, password: str | None = None) -> None:
        self._username = username
        self._key_path = key_path
        self._password = password

    def _build_client(self) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        return client

    def run(self, host: str, command: Sequence[str], *, timeout: int = 60) -> str:
        logger.debug("Executing remote command", extra={"host": host, "command": list(command)})
        client = self._build_client()
        cmd = " ".join(shlex.quote(part) for part in command)
        client.connect(
            hostname=host,
            username=self._username,
            key_filename=self._key_path,
            password=self._password,
            timeout=timeout,
        )
        try:
            stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
            exit_code = stdout.channel.recv_exit_status()
            output = stdout.read().decode("utf-8", "replace")
            error_output = stderr.read().decode("utf-8", "replace")
        finally:
            with suppress(Exception):
                stdin.close()
            with suppress(Exception):
                stdout.close()
            with suppress(Exception):
                stderr.close()
            with suppress(Exception):
                client.close()

        if exit_code != 0:
            logger.error("Remote command failed", extra={"exit_code": exit_code, "stderr": error_output})
            raise RuntimeError(f"Remote command failed (exit {exit_code}): {error_output}")

        return output

    def upload(self, host: str, local_path: str, remote_path: str) -> None:
        logger.debug(
            "Uploading file via SSH",
            extra={"host": host, "local_path": local_path, "remote_path": remote_path},
        )
        client = self._build_client()
        client.connect(
            hostname=host,
            username=self._username,
            key_filename=self._key_path,
            password=self._password,
            timeout=30,
        )
        try:
            sftp = client.open_sftp()
            try:
                sftp.put(local_path, remote_path)
            finally:
                with suppress(Exception):
                    sftp.close()
        finally:
            with suppress(Exception):
                client.close()

    def download(self, host: str, remote_path: str, local_path: str) -> None:
        logger.debug(
            "Downloading file via SSH",
            extra={"host": host, "remote_path": remote_path, "local_path": local_path},
        )
        client = self._build_client()
        client.connect(
            hostname=host,
            username=self._username,
            key_filename=self._key_path,
            password=self._password,
            timeout=30,
        )
        try:
            sftp = client.open_sftp()
            try:
                sftp.get(remote_path, local_path)
            finally:
                with suppress(Exception):
                    sftp.close()
        finally:
            with suppress(Exception):
                client.close()
