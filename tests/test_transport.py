from __future__ import annotations

import asyncio
import traceback
import types

import pytest

from egresskit import (
    EgressRefused,
    GuardedAsyncTransport,
    GuardedTransport,
    SerializationFailed,
)
from egresskit.testing import MockAsyncTransport, MockTransport

from .test_policy import intent


def assert_safe_serialization_error(error: SerializationFailed, marker: str) -> None:
    rendered = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    assert error.__cause__ is None
    assert error.__context__ is None
    assert marker not in error.message
    assert marker not in str(error.to_dict())
    assert marker not in rendered


def test_serialization_error_compatibility_cause_is_discarded() -> None:
    marker = "".join(("protected-compatibility", "-value"))
    cause = ValueError(marker)
    error = SerializationFailed(cause=cause)
    assert error.__cause__ is None
    assert error.__context__ is None
    assert marker not in error.message
    assert marker not in str(error.to_dict())
    assert marker not in str(error.__dict__)


def test_allowed_serializes_then_sends(evaluator: object) -> None:
    events: list[str] = []

    class RecordingTransport(MockTransport):
        def send(self, provider: str, body: bytes) -> bytes:
            events.append("send")
            return super().send(provider, body)

    raw = RecordingTransport()
    guarded = GuardedTransport(evaluator, raw)  # type: ignore[arg-type]

    def serializer(payload: str) -> bytes:
        events.append("serialize")
        return payload.encode()

    result = guarded.dispatch(intent(), "synthetic-value", serializer)
    assert events == ["serialize", "send"]
    assert result.serialized
    assert result.sent
    assert result.response == b"synthetic-response"
    assert raw.calls == [("processor_a", b"synthetic-value")]


def test_denial_never_serializes_or_sends(evaluator: object) -> None:
    raw = MockTransport()
    guarded = GuardedTransport(evaluator, raw)  # type: ignore[arg-type]
    called = False

    def serializer(payload: str) -> bytes:
        nonlocal called
        called = True
        return payload.encode()

    with pytest.raises(EgressRefused) as raised:
        guarded.dispatch(intent(mode="live"), "protected-value", serializer)
    assert not called
    assert raw.calls == []
    error = raised.value.to_dict()
    assert error["error"]["code"] == "egress_refused"
    assert "protected-value" not in str(error)


@pytest.mark.parametrize("mode", ["live", "synthetic"])
def test_dry_run_never_serializes_or_sends(evaluator: object, mode: str) -> None:
    raw = MockTransport()
    guarded = GuardedTransport(evaluator, raw)  # type: ignore[arg-type]
    result = guarded.dispatch(
        intent(mode=mode, dry_run=True),
        "protected-value",
        lambda _: pytest.fail("serializer called in dry run"),
    )
    assert not result.serialized
    assert not result.sent
    assert result.response is None
    assert raw.calls == []


def test_serialization_failure_is_safe(evaluator: object) -> None:
    guarded = GuardedTransport(evaluator, MockTransport())  # type: ignore[arg-type]
    marker = "".join(("protected", "-value"))

    def broken(_: str) -> bytes:
        raise ValueError(marker)

    with pytest.raises(SerializationFailed) as raised:
        guarded.dispatch(intent(), marker, broken)
    assert raised.value.code == "serialization_failed"
    assert_safe_serialization_error(raised.value, marker)


def test_non_bytes_serializer_result_fails_closed(evaluator: object) -> None:
    guarded = GuardedTransport(evaluator, MockTransport())  # type: ignore[arg-type]
    marker = "".join(("protected", "-value"))

    def invalid_serializer(value: str) -> bytes:
        return value  # type: ignore[return-value]

    with pytest.raises(SerializationFailed) as raised:
        guarded.dispatch(intent(), marker, invalid_serializer)
    assert_safe_serialization_error(raised.value, marker)


def test_serialization_failure_suppresses_ambient_exception(evaluator: object) -> None:
    guarded = GuardedTransport(evaluator, MockTransport())  # type: ignore[arg-type]
    marker = "".join(("ambient-protected", "-value"))
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


def test_async_allowed_and_refused(evaluator: object) -> None:
    async def scenario() -> None:
        raw = MockAsyncTransport()
        guarded = GuardedAsyncTransport(evaluator, raw)  # type: ignore[arg-type]

        async def serializer(value: str) -> bytes:
            return value.encode()

        result = await guarded.dispatch(intent(), "synthetic-value", serializer)
        assert result.sent
        assert raw.calls == [("processor_a", b"synthetic-value")]
        with pytest.raises(EgressRefused):
            await guarded.dispatch(intent(mode="live"), "protected-value", serializer)

    asyncio.run(scenario())


def test_async_sync_serializer_and_dry_run(evaluator: object) -> None:
    async def scenario() -> None:
        raw = MockAsyncTransport()
        guarded = GuardedAsyncTransport(evaluator, raw)  # type: ignore[arg-type]
        result = await guarded.dispatch(intent(), "synthetic-value", str.encode)
        assert result.response == b"synthetic-response"
        dry = await guarded.dispatch(
            intent(dry_run=True),
            "protected-value",
            lambda _: pytest.fail("serializer called"),
        )
        assert not dry.sent

    asyncio.run(scenario())


def test_async_serialization_failure(evaluator: object) -> None:
    async def scenario() -> None:
        guarded = GuardedAsyncTransport(evaluator, MockAsyncTransport())  # type: ignore[arg-type]
        marker = "".join(("protected", "-value"))

        async def broken(_: str) -> bytes:
            raise ValueError(marker)

        with pytest.raises(SerializationFailed) as raised:
            await guarded.dispatch(intent(), marker, broken)
        assert_safe_serialization_error(raised.value, marker)

    asyncio.run(scenario())


def test_async_serialization_failure_suppresses_ambient_exception(
    evaluator: object,
) -> None:
    async def scenario() -> None:
        guarded = GuardedAsyncTransport(evaluator, MockAsyncTransport())  # type: ignore[arg-type]
        marker = "".join(("ambient-async-protected", "-value"))
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


def test_async_transport_accepts_every_awaitable_form(evaluator: object) -> None:
    class CustomAwaitable:
        def __init__(self, value: bytes) -> None:
            self.value = value

        def __await__(self):  # type: ignore[no-untyped-def]
            yield from ()
            return self.value

    @types.coroutine
    def generator_serializer(value: str):  # type: ignore[no-untyped-def]
        yield from ()
        return value.encode()

    async def scenario() -> None:
        raw = MockAsyncTransport()
        guarded = GuardedAsyncTransport(evaluator, raw)  # type: ignore[arg-type]

        def future_serializer(value: str) -> asyncio.Future[bytes]:
            future = asyncio.get_running_loop().create_future()
            future.set_result(value.encode())
            return future

        await guarded.dispatch(intent(), "future-value", future_serializer)
        await guarded.dispatch(
            intent(), "custom-value", lambda value: CustomAwaitable(value.encode())
        )
        await guarded.dispatch(intent(), "generator-value", generator_serializer)
        assert raw.calls == [
            ("processor_a", b"future-value"),
            ("processor_a", b"custom-value"),
            ("processor_a", b"generator-value"),
        ]

    asyncio.run(scenario())


def test_transport_exception_passes_through(evaluator: object) -> None:
    class FailingTransport:
        def send(self, provider: str, body: bytes) -> bytes:
            del provider, body
            raise ConnectionError("synthetic transport failure")

    guarded = GuardedTransport(evaluator, FailingTransport())  # type: ignore[arg-type]
    with pytest.raises(ConnectionError, match="synthetic transport failure"):
        guarded.dispatch(intent(), "synthetic-value", str.encode)
