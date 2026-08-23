from __future__ import annotations

import asyncio

import httpx
import pytest

from egresskit import BoundGuardedTransport, Destination, DestinationBindings, PolicyEvaluator
from egresskit.httpx_transport import (
    HTTPXAsyncDestinationTransport,
    HTTPXDestinationTransport,
)

from .conftest import make_policy
from .test_policy import intent


def test_sync_transport_sends_exact_destination_and_bytes() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        response = HTTPXDestinationTransport(client).send(
            Destination.from_url("https://processor.example.test/v1"),
            b"synthetic-body",
        )
    assert response.status_code == 202
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert str(requests[0].url) == "https://processor.example.test/v1"
    assert requests[0].content == b"synthetic-body"


def test_redirect_is_not_followed_when_client_default_enables_it() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            307,
            headers={"location": "https://other.example.test/"},
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        response = HTTPXDestinationTransport(client).send(
            Destination.from_url("https://processor.example.test/v1"), b"fixture"
        )
    assert response.status_code == 307
    assert len(requests) == 1


@pytest.mark.parametrize("method", ["post", "PUT", "Patch"])
def test_body_methods_are_normalized(method: str) -> None:
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        return httpx.Response(200, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        HTTPXDestinationTransport(client, method=method).send(
            Destination.from_url("https://processor.example.test/"), b"fixture"
        )
    assert methods == [method.upper()]


@pytest.mark.parametrize("method", ["GET", "DELETE", "", 7])
def test_non_body_methods_are_rejected(method: object) -> None:
    with (
        httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as client,
        pytest.raises(ValueError, match="POST, PUT, or PATCH"),
    ):
        HTTPXDestinationTransport(client, method=method)  # type: ignore[arg-type]


def test_bound_transport_integrates_before_serialization() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        guarded = BoundGuardedTransport(
            PolicyEvaluator(make_policy()),
            DestinationBindings({"processor_a": "https://processor.example.test/v1"}),
            HTTPXDestinationTransport(client),
        )
        result = guarded.dispatch(intent(), "synthetic-value", str.encode)
    assert result.sent
    assert result.response is not None
    assert result.response.status_code == 200
    assert len(requests) == 1


def test_async_transport_sends_without_following_redirect() -> None:
    async def scenario() -> None:
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                308,
                headers={"location": "https://other.example.test/"},
                request=request,
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), follow_redirects=True
        ) as client:
            response = await HTTPXAsyncDestinationTransport(client).send(
                Destination.from_url("https://processor.example.test/v1"),
                b"synthetic-body",
            )
        assert response.status_code == 308
        assert len(requests) == 1

    asyncio.run(scenario())
