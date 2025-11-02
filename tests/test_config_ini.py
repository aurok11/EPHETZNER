import configparser
import os
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from ephetzner_core import AppConfig, save_config_to_ini


class AppConfigIniTests(unittest.TestCase):
    def test_from_sources_reads_ini_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir, "config.ini")
            config_path.write_text(
                textwrap.dedent(
                    """
                    [ephetzner]
                    s3_endpoint = https://objects.example
                    duckdns_subdomain = lab42
                    ssh_public_key = ssh-ed25519 AAAAexamplekey

                    [ephetzner.secrets]
                    hetzner_api_token = hetzner-secret
                    duckdns_token = duck-secret
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            config = AppConfig.from_sources(ini_path=config_path)

            self.assertEqual("hetzner-secret", config.hetzner_api_token)
            self.assertEqual("duck-secret", config.duckdns_token)
            self.assertEqual("lab42", config.duckdns_subdomain)
            self.assertEqual("https://objects.example", config.s3_endpoint)
            self.assertIsNone(config.s3_access_key)
            self.assertIsNone(config.s3_secret_key)
            self.assertEqual("ssh-ed25519 AAAAexamplekey", config.ssh_public_key)

    def test_env_variables_override_ini_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir, "config.ini")
            config_path.write_text(
                textwrap.dedent(
                    """
                    [ephetzner.secrets]
                    hetzner_api_token = ini-token
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "HETZNER_API_TOKEN": "env-token",
                    "EPHETZNER_SSH_PUBLIC_KEY": "ssh-ed25519 ENVKEY",
                },
                clear=False,
            ):
                config = AppConfig.from_sources(ini_path=config_path)

            self.assertEqual("env-token", config.hetzner_api_token)
            self.assertEqual("ssh-ed25519 ENVKEY", config.ssh_public_key)

    def test_save_config_to_ini_writes_sections(self) -> None:
        config = AppConfig(
            hetzner_api_token="secret-hetzner",
            duckdns_token="secret-duck",
            duckdns_subdomain="lab42",
            s3_endpoint="https://example",
            s3_access_key="access-key",
            s3_secret_key="secret-key",
            ssh_public_key="ssh-ed25519 AAAATestKey",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir, "config.ini")
            save_config_to_ini(config, config_path)

            parser = configparser.ConfigParser()
            parser.read(config_path, encoding="utf-8")

            self.assertEqual("https://example", parser.get("ephetzner", "s3_endpoint"))
            self.assertEqual("lab42", parser.get("ephetzner", "duckdns_subdomain"))
            self.assertEqual(
                "secret-hetzner",
                parser.get("ephetzner.secrets", "hetzner_api_token"),
            )
            self.assertEqual("access-key", parser.get("ephetzner.secrets", "s3_access_key"))
            self.assertEqual("ssh-ed25519 AAAATestKey", parser.get("ephetzner", "ssh_public_key"))

            if os.name == "posix":
                mode = os.stat(config_path).st_mode & 0o777
                self.assertEqual(0o600, mode)


if __name__ == "__main__":  # pragma: no cover - test hook
    unittest.main()
