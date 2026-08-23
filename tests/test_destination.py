from __future__ import annotations

import asyncio
import json
import traceback
import types

import pytest
from hypothesis import given
from hypothesis import strategies as st

from egresskit import (
    BoundGuardedAsyncTransport,
    BoundGuardedTransport,
    Destination,
    DestinationBindings,
    DestinationRefused,
    PolicyEvaluator,
    SerializationFailed,
)
from egresskit.testing import MockAsyncDestinationTransport, MockDestinationTransport

from .conftest import make_policy
from .test_policy import intent


def test_destination_canonicalizes_urls() -> None:
    assert Destination.from_url("https://Processor.Example.Test/v1").url == (
        "https://processor.example.test/v1"
    )
    assert Destination.from_url("https://processor.example.test:8443/").url == (
        "https://processor.example.test:8443/"
    )
    assert Destination.from_url("https://[2001:0db8::1]/v1").url == "https://[2001:db8::1]/v1"
    assert Destination.from_url("https://0xcafe.example.test/").url == (
        "https://0xcafe.example.test/"
    )
    assert Destination.from_url("https://192.0.2.1/v1").url == "https://192.0.2.1/v1"


@pytest.mark.parametrize(
    "url",
    [
        "http://processor.example.test/",
        "https://user@processor.example.test/",
        "https://processor.example.test/?key=value",
        "https://processor.example.test/#fragment",
        "https://processor.example.test/?",
        "https://processor.example.test/#",
        "https://processor.example.test/?#",
        "https://processor.example.test:/",
        "https://[2001:db8::1]:/",
        "https://[v1.com]/",
        "https://[v1.com]:443/",
        "https:///missing-host",
        "https://processor.example.test./",
        "https://processor.example.test/a//b",
        "https://processor.example.test/a/../b",
        "https://processor.example.test/a%2fb",
        "https://processor.example.test:0/",
        "https://processor.example.test:70000/",
        "https://münich.example/",
        " https://processor.example.test/",
        "https://processor.example.test/\n",
        "https://127.1/",
        "https://192.168.001.001/",
        "https://2130706433/",
        "https://0x7f000001/",
        "https://0x7f.0.0.1/",
    ],
)
def test_destination_rejects_ambiguous_or_unsafe_urls(url: str) -> None:
    with pytest.raises(ValueError, match="destination"):
        Destination.from_url(url)


@pytest.mark.parametrize(
    "destination",
    [
        {"host": "Processor.Example.Test"},
        {"host": "processor.example.test", "port": True},
        {"host": "processor.example.test", "port": 0},
        {"host": "processor.example.test", "path": "relative"},
        {"host": "processor.example.test", "path": "/v1?token=value"},
        {"host": "processor.example.test", "path": "/v1#fragment"},
        {"host": "processor.example.test", "path": "/not canonical"},
        {"host": "processor.example.test", "path": "/unicode-\u2603"},
    ],
)
def test_direct_destination_construction_is_validated(destination: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="destination"):
        Destination(**destination)  # type: ignore[arg-type]


def test_bindings_resolve_and_require_exact_destination() -> None:
    bindings = DestinationBindings({"processor_a": "https://processor.example.test/v1"})
    expected = bindings.resolve("processor_a")
    assert expected.url == "https://processor.example.test/v1"
    assert bindings.require("processor_a", expected) is expected
    assert bindings.require("processor_a", expected.url) is expected


def test_bindings_reject_empty_invalid_unknown_and_mismatched() -> None:
    with pytest.raises(ValueError, match="at least one"):
        DestinationBindings({})
    with pytest.raises(ValueError, match="provider identifier"):
        DestinationBindings({"INVALID": "https://processor.example.test/"})

    bindings = DestinationBindings({"processor_a": "https://processor.example.test/"})
    with pytest.raises(DestinationRefused) as unknown:
        bindings.resolve("missing")
    assert unknown.value.reason == "provider_unbound"
    with pytest.raises(DestinationRefused) as mismatch:
        bindings.require("processor_a", "https://other.example.test/")
    error = mismatch.value.to_dict()
    assert error["error"]["reason"] == "destination_mismatch"
    assert "other.example.test" not in json.dumps(error)


def test_bound_transport_resolves_before_serialization(evaluator: object) -> None:
    raw = MockDestinationTransport()
    guarded = BoundGuardedTransport(
        evaluator,  # type: ignore[arg-type]
        DestinationBindings({"processor_a": "https://processor.example.test/v1"}),
        raw,
    )
    result = guarded.dispatch(intent(), "synthetic-value", str.encode)
    assert result.sent
    assert raw.calls == [
        (Destination.from_url("https://processor.example.test/v1"), b"synthetic-value")
    ]


def test_unbound_provider_never_serializes(evaluator: object) -> None:
    guarded = BoundGuardedTransport(
        evaluator,  # type: ignore[arg-type]
        DestinationBindings({"other": "https://other.example.test/"}),
        MockDestinationTransport(),
    )
    with pytest.raises(DestinationRefused):
        guarded.dispatch(
            intent(),
            "protected-value",
            lambda _: pytest.fail("serializer reached for unbound provider"),
        )


def test_bound_dry_run_never_serializes_or_sends(evaluator: object) -> None:
    raw = MockDestinationTransport()
    guarded = BoundGuardedTransport(
        evaluator,  # type: ignore[arg-type]
        DestinationBindings({"processor_a": "https://processor.example.test/"}),
        raw,
    )
    result = guarded.dispatch(
        intent(dry_run=True),
        "protected-value",
        lambda _: pytest.fail("serializer reached in dry run"),
    )
    assert result.decision.allowed
    assert not result.serialized
    assert not result.sent
    assert raw.calls == []


def test_denied_bound_dry_run_does_not_require_binding(evaluator: object) -> None:
    guarded = BoundGuardedTransport(
        evaluator,  # type: ignore[arg-type]
        DestinationBindings({"other": "https://other.example.test/"}),
        MockDestinationTransport(),
    )
    result = guarded.dispatch(
        intent(mode="live", dry_run=True),
        "protected-value",
        lambda _: pytest.fail("serializer reached for denied dry run"),
    )
    assert not result.decision.allowed
    assert not result.sent


def test_async_bound_transport(evaluator: object) -> None:
    async def scenario() -> None:
        raw = MockAsyncDestinationTransport()
        guarded = BoundGuardedAsyncTransport(
            evaluator,  # type: ignore[arg-type]
            DestinationBindings({"processor_a": "https://processor.example.test/v1"}),
            raw,
        )

        async def serializer(value: str) -> bytes:
            return value.encode()

        result = await guarded.dispatch(intent(), "synthetic-value", serializer)
        assert result.sent
        assert raw.calls[0][0].url == "https://processor.example.test/v1"

    asyncio.run(scenario())


def test_bound_serialization_failure_discards_payload_exception(evaluator: object) -> None:
    guarded = BoundGuardedTransport(
        evaluator,  # type: ignore[arg-type]
        DestinationBindings({"processor_a": "https://processor.example.test/v1"}),
        MockDestinationTransport(),
    )
    marker = "".join(("protected-bound", "-value"))

    def broken(_: str) -> bytes:
        raise ValueError(marker)

    with pytest.raises(SerializationFailed) as raised:
        guarded.dispatch(intent(), marker, broken)
    rendered = "".join(
        traceback.format_exception(type(raised.value), raised.value, raised.value.__traceback__)
    )
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert marker not in rendered


def test_bound_serialization_failure_suppresses_ambient_exception(
    evaluator: object,
) -> None:
    guarded = BoundGuardedTransport(
        evaluator,  # type: ignore[arg-type]
        DestinationBindings({"processor_a": "https://processor.example.test/v1"}),
        MockDestinationTransport(),
    )
    marker = "".join(("ambient-bound-protected", "-value"))
    try:
        raise ValueError(marker)
    except ValueError:

        def invalid_serializer(_: str) -> bytes:
            return "not-bytes"  # type: ignore[return-value]

        with pytest.raises(SerializationFailed) as raised:
            guarded.dispatch(intent(), "synthetic-value", invalid_serializer)
    rendered = "".join(
        traceback.format_exception(type(raised.value), raised.value, raised.value.__traceback__)
    )
    assert raised.value.__suppress_context__
    assert marker not in rendered


def test_async_bound_transport_accepts_generator_awaitable_and_discards_failure(
    evaluator: object,
) -> None:
    @types.coroutine
    def generator_serializer(value: str):  # type: ignore[no-untyped-def]
        yield from ()
        return value.encode()

    async def scenario() -> None:
        raw = MockAsyncDestinationTransport()
        guarded = BoundGuardedAsyncTransport(
            evaluator,  # type: ignore[arg-type]
            DestinationBindings({"processor_a": "https://processor.example.test/v1"}),
            raw,
        )
        await guarded.dispatch(intent(), "generator-value", generator_serializer)
        assert raw.calls[0][1] == b"generator-value"
        marker = "".join(("protected-async-bound", "-value"))

        async def broken(_: str) -> bytes:
            raise ValueError(marker)

        with pytest.raises(SerializationFailed) as raised:
            await guarded.dispatch(intent(), marker, broken)
        rendered = "".join(
            traceback.format_exception(type(raised.value), raised.value, raised.value.__traceback__)
        )
        assert raised.value.__cause__ is None
        assert raised.value.__context__ is None
        assert marker not in rendered

    asyncio.run(scenario())


def test_async_bound_serialization_failure_suppresses_ambient_exception(
    evaluator: object,
) -> None:
    async def scenario() -> None:
        guarded = BoundGuardedAsyncTransport(
            evaluator,  # type: ignore[arg-type]
            DestinationBindings({"processor_a": "https://processor.example.test/v1"}),
            MockAsyncDestinationTransport(),
        )
        marker = "".join(("ambient-async-bound-protected", "-value"))
        try:
            raise ValueError(marker)
        except ValueError:
            with pytest.raises(SerializationFailed) as raised:
                await guarded.dispatch(
                    intent(),
                    "synthetic-value",
                    lambda _: "not-bytes",  # type: ignore[arg-type]
                )
        rendered = "".join(
            traceback.format_exception(type(raised.value), raised.value, raised.value.__traceback__)
        )
        assert raised.value.__suppress_context__
        assert marker not in rendered

    asyncio.run(scenario())


@given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=20, max_size=100))
def test_arbitrary_payload_is_absent_from_destination_refusal(random_text: str) -> None:
    payload = f"protected_payload_marker_{random_text}_end"
    guarded = BoundGuardedTransport(
        PolicyEvaluator(make_policy()),
        DestinationBindings({"other": "https://other.example.test/"}),
        MockDestinationTransport(),
    )
    with pytest.raises(DestinationRefused) as raised:
        guarded.dispatch(intent(), payload, str.encode)
    assert payload not in json.dumps(raised.value.to_dict())
