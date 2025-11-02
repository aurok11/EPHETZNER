"""Locale detection and lightweight translation helpers for the ephetzner CLI.

The module centralises locale selection so every command can share the same
language settings. The detection intentionally uses platform specific APIs:

* Linux / POSIX: environment variables (``LC_ALL``, ``LC_MESSAGES``, ``LANG``)
  are inspected first, followed by ``locale.getdefaultlocale`` as a fallback.
* Windows: ``GetUserDefaultLocaleName`` from ``kernel32`` is consulted via
  ``ctypes`` to reflect the user's current display language.

When neither strategy yields a result and the CLI runs interactively, the user
is prompted to select a language. Otherwise English is used as a safe default.
"""

from __future__ import annotations

import locale
import os
import sys
from typing import Dict, Optional

try:  # pragma: no cover - Windows only dependency
    import ctypes
except ImportError:  # pragma: no cover - non-Windows platforms
    ctypes = None

__all__ = [
    "_",
    "get_locale",
    "initialize_locale",
    "set_locale",
]

_SUPPORTED_LOCALES = {"en", "pl"}

def is_supported_locale(locale: str) -> bool:
    """Check if the given locale is supported."""
    return locale in _SUPPORTED_LOCALES
_CURRENT_LOCALE: Optional[str] = None

_TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "pl": {
        "[WARN] Failed to save configuration: {error}": "[WARN] Nie udało się zapisać konfiguracji: {error}",
        " (optional)": " (opcjonalne)",
        "{label}{suffix} – leave blank to keep existing value": "{label}{suffix} – pozostaw puste, aby zachować obecną wartość",
        "{label}{suffix} (current: {value})": "{label}{suffix} (obecnie: {value})",
        "{label}{suffix}": "{label}{suffix}",
        "set": "ustawione",
        "[bold]ephetzner configuration[/bold]": "[bold]Konfiguracja ephetzner[/bold]",
        "Accept the configuration above?": "Czy zaakceptować powyższą konfigurację?",
        "[yellow]Reopening configuration prompts...[/yellow]": "[yellow]Ponownie otwieram kreator konfiguracji...[/yellow]",
        "Configuration": "Konfiguracja",
        "Key": "Klucz",
        "Value": "Wartość",
        "Hetzner API token": "Token API Hetzner",
        "DuckDNS token": "Token DuckDNS",
        "DuckDNS subdomain": "Subdomena DuckDNS",
        "S3 endpoint": "Endpoint S3",
        "S3 access key": "Klucz dostępu S3",
        "S3 secret key": "Klucz tajny S3",
        "Authorized SSH public key": "Autoryzowany klucz publiczny SSH",
        "n/a": "n/d",
        "Provide required values. Leave blank to skip or keep the current value.": "Wprowadź wymagane dane. Pozostaw puste, aby pominąć lub zachować obecną wartość.",
        "Save configuration (including sensitive data) to {path}?": "Zapisać konfigurację (wraz z danymi wrażliwymi) do pliku {path}?",
        "Configuration overview": "Podsumowanie konfiguracji",
        "Provide server name:": "Podaj nazwę serwera:",
        "Server name is required": "Nazwa serwera jest wymagana",
        "Operation summary": "Podsumowanie operacji",
        "Provision server?": "Utworzyć serwer?",
        "Operation cancelled by user": "Operacja anulowana przez użytkownika",
        "Server provisioning is not implemented yet. Check the roadmap.": "Tworzenie serwera nie jest jeszcze zaimplementowane. Sprawdź roadmapę.",
        "Server creation failed: {error}": "Tworzenie serwera nie powiodło się: {error}",
        "[green]Server created successfully: {name} ({identifier})[/green]": "[green]Serwer utworzony pomyślnie: {name} ({identifier})[/green]",
        "DuckDNS update failed: {error}": "Aktualizacja DuckDNS nie powiodła się: {error}",
        "No server types available": "Brak dostępnych typów serwerów",
        "Server type {value} not found": "Nie znaleziono typu serwera: {value}",
        "Select server type": "Wybierz typ serwera",
        "No server type selected": "Nie wybrano typu serwera",
        "No operating system images available": "Brak dostępnych obrazów systemu",
        "Image {value} not found": "Nie znaleziono obrazu: {value}",
        "Select operating system image": "Wybierz obraz systemu",
        "No image selected": "Nie wybrano obrazu",
        "Configure DuckDNS?": "Skonfigurować DuckDNS?",
        "Provide DuckDNS subdomain:": "Podaj subdomenę DuckDNS:",
        "Add a cloud-init script?": "Dodać skrypt cloud-init?",
        "Select script runtime": "Wybierz środowisko wykonania skryptu",
        "Provide path to the script": "Podaj ścieżkę do skryptu",
        "File {path} does not exist": "Plik {path} nie istnieje",
        "Field": "Pole",
        "Server name": "Nazwa serwera",
        "Linked to API token": "Powiązany z tokenem API",
        "Project": "Projekt",
        "Server type": "Typ serwera",
        "Image": "Obraz",
        "DuckDNS": "DuckDNS",
        "Cloud-init": "Cloud-init",
        "None": "Brak",
        "Yes – {detail}": "Tak – {detail}",
        "unnamed": "bez nazwy",
        "SSH key": "Klucz SSH",
        "Configured key ({hint})": "Klucz z konfiguracji ({hint})",
        "Use configured key ({hint})": "Użyj klucza z konfiguracji ({hint})",
        "Paste a new SSH key": "Wklej nowy klucz SSH",
        "Skip SSH key setup": "Pomiń konfigurację klucza SSH",
        "Select SSH key source": "Wybierz źródło klucza SSH",
        "SSH key selection cancelled": "Wybór klucza SSH został anulowany",
        "Selected Hetzner key does not expose a public key": "Wybrany klucz Hetzner nie udostępnia klucza publicznego",
        "Enter SSH public key": "Wprowadź klucz publiczny SSH",
        "SSH public key is required": "Klucz publiczny SSH jest wymagany",
        "New key ({hint})": "Nowy klucz ({hint})",
        "Use Hetzner key {name} ({fingerprint})": "Użyj klucza Hetzner {name} ({fingerprint})",
        "Hetzner key {name} ({fingerprint})": "Klucz Hetzner {name} ({fingerprint})",
        "no fingerprint": "brak odcisku",
        "Deletion confirmation": "Potwierdzenie usunięcia",
        "Continue?": "Kontynuować?",
        "Operation cancelled": "Operacja anulowana",
        "Backup failed": "Backup zakończył się niepowodzeniem",
        "Server deletion is not implemented yet.": "Usuwanie serwerów nie jest jeszcze zaimplementowane.",
        "Server deletion failed: {error}": "Usuwanie serwera nie powiodło się: {error}",
        "[green]Server {name} ({identifier}) deleted successfully.[/green]": "[green]Serwer {name} ({identifier}) został usunięty.[/green]",
        "Server listing is not implemented yet.": "Listing serwerów nie jest jeszcze zaimplementowany.",
        "Failed to fetch server list: {error}": "Nie udało się pobrać listy serwerów: {error}",
        "No servers labeled as Ephemeral": "Brak serwerów oznaczonych jako Ephemeral",
        "Server {identifier} not found": "Nie znaleziono serwera {identifier}",
        "Select server to delete": "Wybierz serwer do usunięcia",
        "no IPv4": "brak IPv4",
        "No server selected": "Nie wybrano serwera",
        "S3 configuration incomplete – skipping backup.": "Konfiguracja S3 niepełna – pomijam backup.",
        "Perform S3 backup?": "Wykonać backup do S3?",
        "Provide remote backup path": "Podaj ścieżkę backupu na serwerze",
        "Provide S3 destination prefix (e.g. s3://bucket/path)": "Podaj prefiks docelowy w S3 (np. s3://bucket/path)",
        "Server": "Serwer",
        "Type": "Typ",
        "IPv4 address": "Adres IPv4",
        "none": "brak",
        "Uptime": "Czas działania",
        "Backup": "Backup",
        "[blue]Starting backup...[/blue]": "[blue]Rozpoczynam backup danych...[/blue]",
        "[red]Backup verification failed[/red]": "[red]Weryfikacja backupu nie powiodła się[/red]",
        "[green]Backup finished: {location}[/green]": "[green]Backup ukończony: {location}[/green]",
        "[yellow]Backup functionality is not available yet.[/yellow]": "[yellow]Funkcja backupu nie jest jeszcze dostępna.[/yellow]",
        "[red]Backup error: {error}[/red]": "[red]Błąd podczas backupu: {error}[/red]",
        "Manage ephetzner configuration files": "Zarządzaj plikami konfiguracji ephetzner",
        "Configuration file already exists: {path}": "Plik konfiguracji już istnieje: {path}",
        "Template saved to {path}": "Szablon zapisany do {path}",
        "Ephemeral Hetzner workspace manager": "Menadżer środowisk Hetzner",
        "Create ephemeral Hetzner workspaces": "Twórz efemeryczne środowiska Hetzner",
    },
}


def _normalize(language: str) -> str:
    """Collapse language identifiers to the supported subset."""

    slug = language.replace("-", "_").lower()
    if slug.startswith("pl"):
        return "pl"
    return "en"


def _detect_locale_windows() -> Optional[str]:
    """Read the UI locale using Windows kernel32 API."""

    if not sys.platform.startswith("win"):
        return None
    if ctypes is None:  # pragma: no cover - imported conditionally
        return None
    try:
        buffer = ctypes.create_unicode_buffer(85)
        if ctypes.windll.kernel32.GetUserDefaultLocaleName(buffer, len(buffer)):  # type: ignore[attr-defined]
            return buffer.value
    except Exception:  # pragma: no cover - defensive catch
        return None
    return None


def _detect_locale_posix() -> Optional[str]:
    """Derive locale from POSIX environment variables or locale settings."""

    if os.name != "posix":
        return None
    for variable in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(variable)
        if value:
            return value
    try:
        default_locale = locale.getdefaultlocale()
    except (AttributeError, ValueError):  # pragma: no cover - platform quirks
        return None
    if default_locale and default_locale[0]:
        return default_locale[0]
    return None


def detect_locale() -> Optional[str]:
    """Return the detected locale code normalised to the supported set."""

    override = os.environ.get("EPHETZNER_LANG")
    if override:
        return _normalize(override)

    detected = _detect_locale_windows() or _detect_locale_posix()
    if detected:
        return _normalize(detected)
    return None


def set_locale(locale_code: str) -> str:
    """Force the application locale to the desired language."""

    global _CURRENT_LOCALE
    normalized = _normalize(locale_code)
    _CURRENT_LOCALE = normalized
    return _CURRENT_LOCALE


def initialize_locale(*, interactive: bool = True) -> str:
    """Ensure a locale is selected, prompting the user if necessary."""

    global _CURRENT_LOCALE
    if _CURRENT_LOCALE:
        return _CURRENT_LOCALE

    detected = detect_locale()
    if detected:
        _CURRENT_LOCALE = detected
        return _CURRENT_LOCALE

    if interactive:
        try:
            import questionary
        except ModuleNotFoundError:  # pragma: no cover - optional dependency
            _CURRENT_LOCALE = "en"
            return _CURRENT_LOCALE

        choice = questionary.select(
            "Select language",  # Default prompt replaced via translations later
            choices=[
                questionary.Choice("English", value="en"),
                questionary.Choice("Polski", value="pl"),
            ],
        ).ask()
        _CURRENT_LOCALE = _normalize(choice or "en")
        return _CURRENT_LOCALE

    _CURRENT_LOCALE = "en"
    return _CURRENT_LOCALE


def get_locale() -> str:
    """Return the active locale, defaulting to English."""

    return _CURRENT_LOCALE or "en"


def _(message: Optional[str]) -> str:
    """Translate the provided message to the currently active locale."""

    if message is None:
        return ""
    active = get_locale()
    if active == "en":
        return message
    catalogue = _TRANSLATIONS.get(active, {})
    return catalogue.get(message, message)