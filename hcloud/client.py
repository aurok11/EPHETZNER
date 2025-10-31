"""Minimal HTTP client for the Hetzner Cloud API."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, Dict, Iterable, Optional

import requests
from requests import Response, Session
from requests import exceptions as requests_exceptions

logger = logging.getLogger(__name__)


class APIException(Exception):
    """Represents an error returned from the Hetzner Cloud API."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class _ResourceClient:
    def __init__(self, client: "Client") -> None:
        self._client = client

    def _request(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        url = f"{self._client.base_url}{path}"
        params = kwargs.pop("params", None)
        json_payload = kwargs.pop("json", None)
        timeout = kwargs.pop("timeout", self._client.timeout)

        try:
            response = self._client._session.request(
                method,
                url,
                params=params,
                json=json_payload,
                timeout=timeout,
            )
        except requests_exceptions.RequestException as exc:  # pragma: no cover - network failure fallback
            logger.error("HTTP request to Hetzner failed", exc_info=exc)
            raise APIException("Failed to communicate with Hetzner Cloud API") from exc

        return self._handle_response(response)

    def _handle_response(self, response: Response) -> Dict[str, Any]:
        if response.status_code >= 400:
            message = response.reason
            try:
                payload = response.json()
            except ValueError:  # pragma: no cover - invalid JSON payload
                payload = None
            if isinstance(payload, dict):
                message = payload.get("error", {}).get("message", message)
            raise APIException(message, status_code=response.status_code)

        if not response.content:
            return {}

        try:
            return response.json()
        except ValueError as exc:  # pragma: no cover - unexpected body
            logger.error("Failed to parse JSON response", exc_info=exc)
            raise APIException("Invalid JSON received from Hetzner Cloud API") from exc


class _ServersClient(_ResourceClient):
    def get_all(self) -> Iterable["_Server"]:
        data = self._request("GET", "/servers")
        servers = data.get("servers", [])
        return [_Server(item) for item in servers]

    def create(self, **payload: Any) -> "_CreateServerResponse":
        data = self._request("POST", "/servers", json=payload)
        return _CreateServerResponse(_Server(data["server"]))

    def delete(self, server: "_Server" | int | str) -> None:
        identifier = _extract_identifier(server)
        self._request("DELETE", f"/servers/{identifier}")

    def get_by_id(self, identifier: int) -> Optional["_Server"]:
        try:
            data = self._request("GET", f"/servers/{identifier}")
        except APIException as exc:
            if exc.status_code == 404:
                return None
            raise
        return _Server(data["server"])

    def get_by_name(self, name: str) -> Optional["_Server"]:
        data = self._request("GET", "/servers", params={"name": name})
        servers = data.get("servers", [])
        if not servers:
            return None
        return _Server(servers[0])

    def update(self, server: "_Server" | int | str, **payload: Any) -> None:
        identifier = _extract_identifier(server)
        self._request("PUT", f"/servers/{identifier}", json=payload)


class _ServerTypesClient(_ResourceClient):
    def get_all(self) -> Iterable["_ServerType"]:
        data = self._request("GET", "/server_types")
        return [_ServerType(item) for item in data.get("server_types", [])]


class _ImagesClient(_ResourceClient):
    def get_all(self, **params: Any) -> Iterable["_Image"]:
        data = self._request("GET", "/images", params=params)
        return [_Image(item) for item in data.get("images", [])]


class _CreateServerResponse:
    def __init__(self, server: "_Server") -> None:
        self.server = server


class _Price:
    def __init__(self, payload: Dict[str, Any]) -> None:
        price_hourly = payload.get("price_hourly")
        if isinstance(price_hourly, dict):
            self.price_hourly = SimpleNamespace(**price_hourly)
        else:
            self.price_hourly = price_hourly


class _ServerType:
    def __init__(self, payload: Dict[str, Any]) -> None:
        self.id = payload.get("id")
        self.name = payload.get("name")
        self.cores = payload.get("cores", 0)
        self.memory = payload.get("memory", 0)
        self.disk = payload.get("disk", 0)
        self.prices = [_Price(item) for item in payload.get("prices", [])]


class _Image:
    def __init__(self, payload: Dict[str, Any]) -> None:
        self.id = payload.get("id")
        self.name = payload.get("name")
        self.description = payload.get("description")


class _Address:
    def __init__(self, payload: Dict[str, Any] | None) -> None:
        self.ip = None
        if payload:
            self.ip = payload.get("ip")


class _PublicNet:
    def __init__(self, payload: Dict[str, Any] | None) -> None:
        ipv4 = payload.get("ipv4") if payload else None
        ipv6 = payload.get("ipv6") if payload else None
        self.ipv4 = _Address(ipv4) if ipv4 else None
        self.ipv6 = _Address(ipv6) if ipv6 else None


class _Server:
    def __init__(self, payload: Dict[str, Any]) -> None:
        self.id = payload.get("id")
        self.name = payload.get("name")
        self.server_type = _ServerType(payload.get("server_type", {}))
        self.image = _Image(payload.get("image", {})) if payload.get("image") else None
        self.public_net = _PublicNet(payload.get("public_net"))
        self.created = payload.get("created")
        self.labels = payload.get("labels", {})


def _extract_identifier(server: "_Server" | int | str) -> int | str:
    if isinstance(server, (int, str)):
        return server
    return server.id


class Client:
    """HTTP API client mirroring the upstream ``hcloud.Client`` interface."""

    def __init__(
        self,
        token: str,
        *,
        base_url: str = "https://api.hetzner.cloud/v1",
        timeout: int = 30,
        session: Session | None = None,
    ) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = session or requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )
        self.servers = _ServersClient(self)
        self.server_types = _ServerTypesClient(self)
        self.images = _ImagesClient(self)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"Client(base_url={self.base_url!r})"
