"""Application configuration management for ephetzner CLI."""

from __future__ import annotations

import configparser
import os
import sys
from contextlib import suppress
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ValidationError

from .localization import _

class _EnvConfig(BaseModel):
    """Validation schema for environment-provided configuration values."""

    hetzner_api_token: Optional[str] = None
    duckdns_token: Optional[str] = None
    duckdns_subdomain: Optional[str] = None
    s3_endpoint: Optional[str] = None
    s3_access_key: Optional[str] = None
    s3_secret_key: Optional[str] = None
    ssh_public_key: Optional[str] = None


@dataclass(slots=True)
class AppConfig:
    """Mutable application configuration resolved at runtime."""

    hetzner_api_token: Optional[str]
    duckdns_token: Optional[str]
    duckdns_subdomain: Optional[str]
    s3_endpoint: Optional[str]
    s3_access_key: Optional[str]
    s3_secret_key: Optional[str]
    ssh_public_key: Optional[str] = None

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Load configuration from environment variables."""
        try:
            data = _EnvConfig(
                hetzner_api_token=_get_env("HETZNER_API_TOKEN"),
                duckdns_token=_get_env("DUCKDNS_TOKEN"),
                duckdns_subdomain=_get_env("DUCKDNS_SUBDOMAIN"),
                s3_endpoint=_get_env("S3_ENDPOINT"),
                s3_access_key=_get_env("S3_ACCESS_KEY"),
                s3_secret_key=_get_env("S3_SECRET_KEY"),
                ssh_public_key=_get_env("EPHETZNER_SSH_PUBLIC_KEY"),
            )
        except ValidationError as exc:  # pragma: no cover - defensive guard
            raise RuntimeError("Failed to validate environment configuration") from exc
        return cls(**data.model_dump())

    @classmethod
    def from_sources(cls, *, ini_path: Path | None = None) -> "AppConfig":
        """Load configuration from ini file and environment variables."""

        merged: dict[str, Optional[str]] = {}
        if ini_path and ini_path.exists():
            merged.update(_load_ini_values(ini_path))

        env_config = cls.from_env()
        for field in _CONFIG_FIELDS:
            value = getattr(env_config, field)
            if value is not None:
                merged[field] = value
            else:
                merged.setdefault(field, getattr(env_config, field))

        return cls(**{name: merged.get(name) for name in _CONFIG_FIELDS})


def resolve_default_config_path() -> Path:
    """Return path to default configuration file location."""

    if _is_frozen_binary():
        executable = Path(sys.executable).resolve()
        return executable.parent / "ephetzner.ini"
    return Path("~/.config/ephetzner/config.ini").expanduser()


def resolve_config_path() -> Path:
    """Resolve configuration file path, honoring environment overrides."""

    override = os.getenv("EPHETZNER_CONFIG_PATH")
    if override:
        return Path(override).expanduser()
    return resolve_default_config_path()


def resolve_config(
    interactive: bool = True,
    *,
    config_path: Path | None = None,
    persist_prompt: bool = True,
) -> AppConfig:
    """Build application configuration, optionally prompting for missing values."""

    path = config_path or resolve_config_path()
    config = AppConfig.from_sources(ini_path=path)
    if not interactive:
        return config

    from ui.menus import prompt_app_config  # Imported lazily to avoid cycles

    updated = prompt_app_config(config)
    if persist_prompt:
        _maybe_persist_config(updated, path)
    return updated


def with_overrides(config: AppConfig, **overrides: Optional[str]) -> AppConfig:
    """Return new configuration instance with the provided field overrides."""

    return replace(config, **overrides)


def save_config_to_ini(config: AppConfig, path: Path) -> None:
    """Persist configuration values to an ini file, separating secrets."""

    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # Preserve field case

    general: dict[str, str] = {}
    secrets: dict[str, str] = {}

    for field in _CONFIG_FIELDS:
        value = getattr(config, field)
        if not value:
            continue
        target = secrets if field in _SENSITIVE_FIELDS else general
        target[field] = value

    parser[CONFIG_SECTION] = general
    if secrets:
        parser[SECRETS_SECTION] = secrets

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        parser.write(handle)

    with suppress(PermissionError, NotImplementedError):
        os.chmod(path, 0o600)


def _get_env(key: str) -> Optional[str]:
    """Return environment variable value with blank strings normalized to None."""
    value = os.getenv(key)
    if value is None:
        return None
    value = value.strip()
    return value or None


CONFIG_SECTION = "ephetzner"
SECRETS_SECTION = "ephetzner.secrets"
_CONFIG_FIELDS = (
    "hetzner_api_token",
    "duckdns_token",
    "duckdns_subdomain",
    "s3_endpoint",
    "s3_access_key",
    "s3_secret_key",
    "ssh_public_key",
)
_SENSITIVE_FIELDS = {
    "hetzner_api_token",
    "duckdns_token",
    "s3_access_key",
    "s3_secret_key",
}


def _load_ini_values(path: Path) -> dict[str, Optional[str]]:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    if not parser.read(path, encoding="utf-8"):
        return {}

    values: dict[str, Optional[str]] = {}
    for field in _CONFIG_FIELDS:
        section = SECRETS_SECTION if field in _SENSITIVE_FIELDS else CONFIG_SECTION
        if parser.has_option(section, field):
            raw = parser.get(section, field)
            values[field] = raw.strip() or None
    return values


def _maybe_persist_config(config: AppConfig, path: Path) -> None:
    try:
        from questionary import confirm
    except ModuleNotFoundError:  # pragma: no cover - defensive guard
        return

    message = _(
        "Save configuration (including sensitive data) to {path}?"
    ).format(path=path)
    should_save = confirm(message, default=False).ask()
    if not should_save:
        return

    try:
        save_config_to_ini(config, path)
    except Exception as exc:  # pragma: no cover - defensive guard
        print(_("[WARN] Failed to save configuration: {error}").format(error=exc))



def _is_frozen_binary() -> bool:
    """Return True when running from a PyInstaller-style frozen binary."""

    return bool(getattr(sys, "frozen", False))
