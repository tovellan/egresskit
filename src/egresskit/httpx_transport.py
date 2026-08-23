"""Optional HTTPX adapters for validated EgressKit destinations."""

from __future__ import annotations

import httpx

from .destination import Destination

_BODY_METHODS = frozenset({"PATCH", "POST", "PUT"})


class HTTPXDestinationTransport:
    """Send bytes with a caller-owned synchronous HTTPX client."""

    def __init__(self, client: httpx.Client, *, method: str = "POST") -> None:
        self._client = client
        self._method = _normalize_method(method)

    def send(self, destination: Destination, body: bytes) -> httpx.Response:
        return self._client.request(
            self._method,
            destination.url,
            content=body,
            follow_redirects=False,
        )


class HTTPXAsyncDestinationTransport:
    """Send bytes with a caller-owned asynchronous HTTPX client."""

    def __init__(self, client: httpx.AsyncClient, *, method: str = "POST") -> None:
        self._client = client
        self._method = _normalize_method(method)

    async def send(self, destination: Destination, body: bytes) -> httpx.Response:
        return await self._client.request(
            self._method,
            destination.url,
            content=body,
            follow_redirects=False,
        )


def _normalize_method(value: str) -> str:
    if not isinstance(value, str) or value.upper() not in _BODY_METHODS:
        raise ValueError("HTTPX destination method must be POST, PUT, or PATCH")
    return value.upper()
