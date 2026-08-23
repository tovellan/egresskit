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


def test_safe_client_defaults_preserve_exact_nondefault_port() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, request=request)

    with httpx.Client(
        base_url="https://unused.example.test/base",
        headers={"authorization": "Bearer synthetic-token"},
        transport=httpx.MockTransport(handler),
    ) as client:
        HTTPXDestinationTransport(client).send(
            Destination.from_url("https://processor.example.test:8443/v1"),
            b"fixture",
        )
    assert str(requests[0].url) == "https://processor.example.test:8443/v1"
    assert requests[0].headers["host"] == "processor.example.test:8443"
    assert requests[0].headers["authorization"] == "Bearer synthetic-token"


@pytest.mark.parametrize(
    "client_options",
    [
        {"params": {"tenant": "other"}},
        {"headers": {"host": "other.example.test"}},
        {"auth": ("synthetic-user", "synthetic-password")},
        {"event_hooks": {"request": [lambda request: None]}},
    ],
)
def test_destination_mutating_client_configuration_is_rejected(
    client_options: dict[str, object],
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, request=request)

    with (
        httpx.Client(
            transport=httpx.MockTransport(handler),
            **client_options,  # type: ignore[arg-type]
        ) as client,
        pytest.raises(ValueError, match="validated destination"),
    ):
        HTTPXDestinationTransport(client)
    assert calls == []


def test_client_mutation_after_adapter_construction_fails_before_send() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        transport = HTTPXDestinationTransport(client)
        client.params = httpx.QueryParams({"tenant": "other"})
        with pytest.raises(ValueError, match="validated destination"):
            transport.send(Destination.from_url("https://processor.example.test/v1"), b"fixture")
    assert calls == []


def test_sync_transport_rejects_async_client_kind() -> None:
    async def scenario() -> None:
        calls: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(TypeError, match=r"httpx\.Client"):
                HTTPXDestinationTransport(client)  # type: ignore[arg-type]
        assert calls == []

    asyncio.run(scenario())


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


def test_active_method_subclass_is_rejected_before_execution() -> None:
    marker = "active-httpx-method-marker"

    class ActiveMethod(str):
        def upper(self) -> str:
            raise RuntimeError(marker)

    with (
        httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as client,
        pytest.raises(ValueError, match="POST, PUT, or PATCH"),
    ):
        HTTPXDestinationTransport(client, method=ActiveMethod("POST"))

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200))
        ) as client:
            with pytest.raises(ValueError, match="POST, PUT, or PATCH"):
                HTTPXAsyncDestinationTransport(client, method=ActiveMethod("POST"))

    asyncio.run(scenario())


def test_sync_transport_rejects_active_request_value_subclasses() -> None:
    marker = "active-httpx-request-marker"
    requests: list[httpx.Request] = []

    class ActiveDestination(Destination):
        def __post_init__(self) -> None:
            pass

        @property
        def url(self) -> str:
            raise RuntimeError(marker)

    class ActiveBytes(bytes):
        def __len__(self) -> int:
            raise RuntimeError(marker)

        def __iter__(self):  # type: ignore[no-untyped-def]
            raise RuntimeError(marker)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        transport = HTTPXDestinationTransport(client)
        with pytest.raises(ValueError, match="exact Destination"):
            transport.send(ActiveDestination(host="processor.example.test"), b"fixture")
        with pytest.raises(ValueError, match="exact built-in bytes"):
            transport.send(
                Destination.from_url("https://processor.example.test/"),
                ActiveBytes(b"fixture"),
            )
    assert requests == []


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


def test_async_transport_rejects_destination_mutating_defaults() -> None:
    async def scenario() -> None:
        calls: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, request=request)

        async with httpx.AsyncClient(
            params={"tenant": "other"}, transport=httpx.MockTransport(handler)
        ) as client:
            with pytest.raises(ValueError, match="validated destination"):
                HTTPXAsyncDestinationTransport(client)
        assert calls == []

    asyncio.run(scenario())


def test_async_transport_rejects_sync_client_kind() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, request=request)

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(TypeError, match=r"httpx\.AsyncClient"),
    ):
        HTTPXAsyncDestinationTransport(client)  # type: ignore[arg-type]
    assert calls == []


def test_async_transport_rejects_active_request_value_subclasses() -> None:
    marker = "active-async-httpx-request-marker"

    class ActiveDestination(Destination):
        def __post_init__(self) -> None:
            pass

        @property
        def url(self) -> str:
            raise RuntimeError(marker)

    class ActiveBytes(bytes):
        def __len__(self) -> int:
            raise RuntimeError(marker)

        def __iter__(self):  # type: ignore[no-untyped-def]
            raise RuntimeError(marker)

    async def scenario() -> None:
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            transport = HTTPXAsyncDestinationTransport(client)
            with pytest.raises(ValueError, match="exact Destination"):
                await transport.send(ActiveDestination(host="processor.example.test"), b"fixture")
            with pytest.raises(ValueError, match="exact built-in bytes"):
                await transport.send(
                    Destination.from_url("https://processor.example.test/"),
                    ActiveBytes(b"fixture"),
                )
        assert requests == []

    asyncio.run(scenario())
