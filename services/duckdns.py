"""DuckDNS integration implementing the DNSProvider contract."""

from __future__ import annotations

import logging

import requests
from requests import Session
from requests import exceptions as requests_exceptions

from services.base import DNSProvider


logger = logging.getLogger(__name__)


class DuckDNSProvider(DNSProvider):
    """Interact with DuckDNS API to update dynamic DNS records."""

    BASE_URL = "https://www.duckdns.org/update"

    def __init__(self, token: str, session: Session | None = None) -> None:
        self._token = token
        self._session = session or requests.Session()
        headers = getattr(self._session, "headers", None)
        if headers is not None:
            headers.update({"User-Agent": "ephetzner/0.1"})

    def update_record(self, host: str, ipv4: str, *, ttl: int = 60) -> None:
        logger.info("Updating DuckDNS record", extra={"host": host, "ttl": ttl})
        params = {
            "domains": host,
            "token": self._token,
            "ip": ipv4,
        }
        if not ipv4:
            params["clear"] = "true"

        try:
            response = self._session.get(self.BASE_URL, params=params, timeout=15)
        except requests_exceptions.RequestException as exc:
            logger.error("DuckDNS request failed", exc_info=exc)
            raise RuntimeError("DuckDNS request failed") from exc

        payload = response.text.strip()
        if payload.upper() != "OK":
            logger.error("DuckDNS responded with failure", extra={"response": payload})
            raise RuntimeError(f"DuckDNS update failed: {payload}")

        logger.info("DuckDNS record updated successfully", extra={"host": host})
