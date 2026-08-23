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
        url, validated_body = _validate_request_values(destination, body)
        request = _build_request(
            self._client,
            self._method,
            url,
            content=validated_body,
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
        url, validated_body = _validate_request_values(destination, body)
        request = _build_request(
            self._client,
            self._method,
            url,
            content=validated_body,
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


def _validate_request_values(destination: object, body: object) -> tuple[str, bytes]:
    if type(destination) is not Destination:
        raise ValueError("HTTPX destination must be an exact Destination")
    if type(body) is not bytes:
        raise ValueError("HTTPX body must be exact built-in bytes")
    return destination.url, body


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
    if type(value) is not str:
        raise ValueError("HTTPX destination method must be POST, PUT, or PATCH")
    normalized = value.upper()
    if normalized not in _BODY_METHODS:
        raise ValueError("HTTPX destination method must be POST, PUT, or PATCH")
    return normalized
