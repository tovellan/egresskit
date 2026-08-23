from __future__ import annotations

import asyncio

import pytest

from egresskit import (
    EgressRefused,
    GuardedAsyncTransport,
    GuardedTransport,
    SerializationFailed,
)
from egresskit.testing import MockAsyncTransport, MockTransport

from .test_policy import intent


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

    def broken(_: str) -> bytes:
        raise ValueError("protected-value")

    with pytest.raises(SerializationFailed) as raised:
        guarded.dispatch(intent(), "protected-value", broken)
    assert raised.value.code == "serialization_failed"
    assert "protected-value" not in raised.value.message


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

        async def broken(_: str) -> bytes:
            raise ValueError("protected-value")

        with pytest.raises(SerializationFailed):
            await guarded.dispatch(intent(), "protected-value", broken)

    asyncio.run(scenario())


def test_transport_exception_passes_through(evaluator: object) -> None:
    class FailingTransport:
        def send(self, provider: str, body: bytes) -> bytes:
            del provider, body
            raise ConnectionError("synthetic transport failure")

    guarded = GuardedTransport(evaluator, FailingTransport())  # type: ignore[arg-type]
    with pytest.raises(ConnectionError, match="synthetic transport failure"):
        guarded.dispatch(intent(), "synthetic-value", str.encode)
