"""Tests for DuckDNSProvider behaviour."""

from __future__ import annotations

import unittest

from requests import exceptions as requests_exceptions

from services.duckdns import DuckDNSProvider


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text
        self.status_code = 200
        self.content = text.encode("utf-8")

    def json(self):  # pragma: no cover - DuckDNS returns plain text
        raise ValueError("DuckDNS responses are plain text")


class _FakeSession:
    def __init__(self, response: _FakeResponse | Exception) -> None:
        self.response = response
        self.calls: list[dict] = []

    def get(self, url: str, *, params: dict, timeout: int):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class DuckDNSProviderTests(unittest.TestCase):
    """Validate success and failure scenarios for DuckDNS updates."""

    def test_update_record_success(self) -> None:
        session = _FakeSession(_FakeResponse("OK"))
        provider = DuckDNSProvider(token="abc", session=session)  # type: ignore[arg-type]

        provider.update_record("example", "203.0.113.5")

        self.assertEqual(len(session.calls), 1)
        params = session.calls[0]["params"]
        self.assertEqual(params["domains"], "example")
        self.assertEqual(params["ip"], "203.0.113.5")
        self.assertNotIn("clear", params)

    def test_update_record_clears_when_ip_missing(self) -> None:
        session = _FakeSession(_FakeResponse("OK"))
        provider = DuckDNSProvider(token="abc", session=session)  # type: ignore[arg-type]

        provider.update_record("example", "")

        params = session.calls[0]["params"]
        self.assertEqual(params["clear"], "true")

    def test_update_record_failure_text(self) -> None:
        session = _FakeSession(_FakeResponse("KO"))
        provider = DuckDNSProvider(token="abc", session=session)  # type: ignore[arg-type]

        with self.assertRaises(RuntimeError):
            provider.update_record("example", "1.2.3.4")

    def test_update_record_network_failure(self) -> None:
        session = _FakeSession(requests_exceptions.Timeout("boom"))
        provider = DuckDNSProvider(token="abc", session=session)  # type: ignore[arg-type]

        with self.assertRaises(RuntimeError):
            provider.update_record("example", "1.2.3.4")


if __name__ == "__main__":  # pragma: no cover - convenience
    unittest.main()
