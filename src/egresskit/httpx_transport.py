"""Optional HTTPX adapters for validated EgressKit destinations."""

from __future__ import annotations

import httpx

from .destination import Destination

_BODY_METHODS = frozenset({"PATCH", "POST", "PUT"})


class HTTPXDestinationTransport:
    """Send bytes with a caller-owned synchronous HTTPX client."""

    def __init__(self, client: httpx.Client, *, method: str = "POST") -> None:
        if not isinstance(client, httpx.Client):
            raise TypeError("synchronous HTTPX transport requires httpx.Client")
        _validate_client(client)
        self._client = client
        self._method = _normalize_method(method)

    def send(self, destination: Destination, body: bytes) -> httpx.Response:
        request = _build_request(
            self._client,
            self._method,
            destination.url,
            content=body,
        )
        return self._client.send(request, auth=None, follow_redirects=False)


class HTTPXAsyncDestinationTransport:
    """Send bytes with a caller-owned asynchronous HTTPX client."""

    def __init__(self, client: httpx.AsyncClient, *, method: str = "POST") -> None:
        if not isinstance(client, httpx.AsyncClient):
            raise TypeError("asynchronous HTTPX transport requires httpx.AsyncClient")
        _validate_client(client)
        self._client = client
        self._method = _normalize_method(method)

    async def send(self, destination: Destination, body: bytes) -> httpx.Response:
        request = _build_request(
            self._client,
            self._method,
            destination.url,
            content=body,
        )
        return await self._client.send(request, auth=None, follow_redirects=False)


def _validate_client(client: httpx.Client | httpx.AsyncClient) -> None:
    if (
        client.params
        or "host" in client.headers
        or client.auth is not None
        or client.event_hooks.get("request")
    ):
        raise ValueError("HTTPX client configuration can change the validated destination")


def _build_request(
    client: httpx.Client | httpx.AsyncClient,
    method: str,
    url: str,
    *,
    content: bytes,
) -> httpx.Request:
    _validate_client(client)
    request = client.build_request(method, url, content=content)
    expected_url = httpx.URL(url)
    expected_host = httpx.Request(method, expected_url).headers["host"]
    if request.url != expected_url or request.headers.get("host") != expected_host:
        raise ValueError("HTTPX client configuration can change the validated destination")
    return request


def _normalize_method(value: str) -> str:
    if not isinstance(value, str) or value.upper() not in _BODY_METHODS:
        raise ValueError("HTTPX destination method must be POST, PUT, or PATCH")
    return value.upper()
