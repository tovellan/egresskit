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


def test_destination_rejects_active_value_subclasses_before_methods_run() -> None:
    marker = "active-destination-subclass-marker"

    class ActiveString(str):
        def isascii(self) -> bool:
            raise RuntimeError(marker)

        def __iter__(self):  # type: ignore[no-untyped-def]
            raise RuntimeError(marker)

        def __format__(self, format_spec: str) -> str:
            del format_spec
            raise RuntimeError(marker)

    class ActivePort(int):
        def __format__(self, format_spec: str) -> str:
            del format_spec
            raise RuntimeError(marker)

    class ActiveDestination(Destination):
        def __new__(cls, *args: object, **kwargs: object) -> ActiveDestination:
            del args, kwargs
            raise RuntimeError(marker)

    with pytest.raises(ValueError, match=r"^destination type is invalid$"):
        ActiveDestination.from_url("https://processor.example.test/")
    with pytest.raises(ValueError, match=r"^destination URL is invalid$"):
        Destination.from_url(ActiveString("https://processor.example.test/"))
    with pytest.raises(ValueError, match=r"^destination host is invalid$"):
        Destination(host=ActiveString("processor.example.test"))
    with pytest.raises(ValueError, match=r"^destination path is invalid$"):
        Destination(host="processor.example.test", path=ActiveString("/v1"))
    with pytest.raises(ValueError, match=r"^destination port is invalid$"):
        Destination(host="processor.example.test", port=ActivePort(443))


def test_bindings_reject_active_destination_subclasses_before_methods_run() -> None:
    marker = "active-destination-object-marker"

    class ActiveDestination(Destination):
        def __post_init__(self) -> None:
            pass

        @property
        def url(self) -> str:
            raise RuntimeError(marker)

    active = ActiveDestination(host="processor.example.test")
    with pytest.raises(ValueError, match=r"^destination binding is invalid$"):
        DestinationBindings({"processor_a": active})

    bindings = DestinationBindings({"processor_a": "https://processor.example.test/"})
    with pytest.raises(ValueError, match=r"^destination binding is invalid$"):
        bindings.require("processor_a", active)


def test_malformed_destination_tracebacks_do_not_reflect_rejected_value() -> None:
    marker = "protected-invalid-port-marker"
    url = f"https://processor.example.test:{marker}/"

    with pytest.raises(ValueError, match=r"^destination URL is invalid$") as direct:
        Destination.from_url(url)
    direct_traceback = "".join(
        traceback.format_exception(type(direct.value), direct.value, direct.value.__traceback__)
    )
    assert direct.value.__cause__ is None
    assert direct.value.__context__ is None
    assert direct.value.__suppress_context__
    assert marker not in direct_traceback

    bindings = DestinationBindings({"processor_a": "https://processor.example.test/"})
    with pytest.raises(ValueError, match=r"^destination URL is invalid$") as required:
        bindings.require("processor_a", url)
    required_traceback = "".join(
        traceback.format_exception(
            type(required.value), required.value, required.value.__traceback__
        )
    )
    assert required.value.__cause__ is None
    assert required.value.__context__ is None
    assert required.value.__suppress_context__
    assert marker not in required_traceback


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
    assert unknown.value.provider is None
    assert "provider" not in unknown.value.to_dict()["error"]
    with pytest.raises(DestinationRefused) as mismatch:
        bindings.require("processor_a", "https://other.example.test/")
    error = mismatch.value.to_dict()
    assert error["error"]["reason"] == "destination_mismatch"
    assert error["error"]["provider"] == "processor_a"
    assert "other.example.test" not in json.dumps(error)


@pytest.mark.parametrize(
    "provider",
    [
        "",
        "INVALID",
        "invalid/provider",
        "sk-live-sensitive/token-value",
        "a" * 129,
        None,
        7,
    ],
)
def test_public_binding_lookup_rejects_invalid_provider_without_reflection(
    provider: object,
) -> None:
    bindings = DestinationBindings({"processor_a": "https://processor.example.test/"})
    marker = provider if type(provider) is str else repr(provider)
    with pytest.raises(ValueError, match=r"^provider identifier is invalid$") as resolved:
        bindings.resolve(provider)  # type: ignore[arg-type]
    resolved_traceback = "".join(
        traceback.format_exception(
            type(resolved.value), resolved.value, resolved.value.__traceback__
        )
    )
    assert str(resolved.value) == "provider identifier is invalid"
    if marker:
        assert marker not in resolved_traceback

    with pytest.raises(ValueError, match=r"^provider identifier is invalid$") as required:
        bindings.require(provider, "https://processor.example.test/")  # type: ignore[arg-type]
    required_traceback = "".join(
        traceback.format_exception(
            type(required.value), required.value, required.value.__traceback__
        )
    )
    assert str(required.value) == "provider identifier is invalid"
    if marker:
        assert marker not in required_traceback


def test_public_binding_lookup_rejects_hostile_string_subclasses() -> None:
    class HostileProvider(str):
        def __len__(self) -> int:
            pytest.fail("provider subclass length executed")

        def __hash__(self) -> int:
            pytest.fail("provider subclass hash executed")

        def __eq__(self, other: object) -> bool:
            del other
            pytest.fail("provider subclass equality executed")

    bindings = DestinationBindings({"processor_a": "https://processor.example.test/"})
    provider = HostileProvider("processor_a")
    with pytest.raises(ValueError, match=r"^provider identifier is invalid$"):
        bindings.resolve(provider)
    with pytest.raises(ValueError, match=r"^provider identifier is invalid$"):
        bindings.require(provider, "https://processor.example.test/")


def test_valid_unbound_provider_lookup_never_reflects_caller_value() -> None:
    bindings = DestinationBindings({"processor_a": "https://processor.example.test/"})
    marker = "sk_live_sensitive_token_value"

    operations = (
        lambda: bindings.resolve(marker),
        lambda: bindings.require(marker, "https://processor.example.test/"),
    )
    for operation in operations:
        with pytest.raises(DestinationRefused) as raised:
            operation()
        rendered = "".join(
            traceback.format_exception(type(raised.value), raised.value, raised.value.__traceback__)
        )
        error = raised.value.to_dict()
        assert raised.value.reason == "provider_unbound"
        assert raised.value.provider is None
        assert raised.value.__cause__ is None
        assert raised.value.__context__ is None
        assert "provider" not in error["error"]
        assert marker not in str(raised.value)
        assert marker not in repr(raised.value)
        assert marker not in repr(raised.value.__dict__)
        assert marker not in json.dumps(error)
        assert marker not in rendered


def test_destination_mismatch_suppresses_ambient_exception_display() -> None:
    bindings = DestinationBindings({"processor_a": "https://processor.example.test/"})
    marker = "caller-selected-destination-marker"
    try:
        raise RuntimeError(marker)
    except RuntimeError:
        with pytest.raises(DestinationRefused) as raised:
            bindings.require("processor_a", "https://other.example.test/")
    rendered = "".join(
        traceback.format_exception(type(raised.value), raised.value, raised.value.__traceback__)
    )
    assert raised.value.reason == "destination_mismatch"
    assert raised.value.provider == "processor_a"
    assert raised.value.__suppress_context__
    assert marker not in rendered


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
