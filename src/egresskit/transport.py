"""Enforcement points that authorize before serialization and transport execution."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from inspect import isawaitable
from typing import Generic, Protocol, TypeVar

from .errors import EgressRefused, SerializationFailed
from .models import Decision, EgressIntent
from .policy import PolicyEvaluator

PayloadT = TypeVar("PayloadT")
ResponseT = TypeVar("ResponseT", covariant=True)


class Transport(Protocol[ResponseT]):
    def send(self, provider: str, body: bytes) -> ResponseT: ...


class AsyncTransport(Protocol[ResponseT]):
    async def send(self, provider: str, body: bytes) -> ResponseT: ...


def _serialize_payload(
    payload: PayloadT,
    serializer: Callable[[PayloadT], bytes],
) -> tuple[bool, bytes | None]:
    try:
        body = serializer(payload)
    except Exception:
        return False, None
    return (True, body) if isinstance(body, bytes) else (False, None)


async def _serialize_payload_async(
    payload: PayloadT,
    serializer: Callable[[PayloadT], bytes] | Callable[[PayloadT], Awaitable[bytes]],
) -> tuple[bool, bytes | None]:
    try:
        serialized = serializer(payload)
        body = await serialized if isawaitable(serialized) else serialized
    except Exception:
        return False, None
    return (True, body) if isinstance(body, bytes) else (False, None)


@dataclass(frozen=True)
class DispatchResult(Generic[ResponseT]):
    decision: Decision
    serialized: bool
    sent: bool
    response: ResponseT | None


class GuardedTransport(Generic[ResponseT]):
    """The intended application boundary for synchronous outbound calls."""

    def __init__(self, evaluator: PolicyEvaluator, transport: Transport[ResponseT]) -> None:
        self._evaluator = evaluator
        self._transport = transport

    def dispatch(
        self,
        intent: EgressIntent,
        payload: PayloadT,
        serializer: Callable[[PayloadT], bytes],
    ) -> DispatchResult[ResponseT]:
        decision = self._evaluator.evaluate(intent)
        if intent.context.dry_run:
            return DispatchResult(decision=decision, serialized=False, sent=False, response=None)
        if not decision.allowed:
            raise EgressRefused(decision)
        serialized, body = _serialize_payload(payload, serializer)
        if not serialized or body is None:
            del payload, serializer
            raise SerializationFailed() from None
        response = self._transport.send(intent.provider, body)
        return DispatchResult(decision=decision, serialized=True, sent=True, response=response)


class GuardedAsyncTransport(Generic[ResponseT]):
    """The intended application boundary for asynchronous outbound calls."""

    def __init__(self, evaluator: PolicyEvaluator, transport: AsyncTransport[ResponseT]) -> None:
        self._evaluator = evaluator
        self._transport = transport

    async def dispatch(
        self,
        intent: EgressIntent,
        payload: PayloadT,
        serializer: Callable[[PayloadT], bytes] | Callable[[PayloadT], Awaitable[bytes]],
    ) -> DispatchResult[ResponseT]:
        decision = self._evaluator.evaluate(intent)
        if intent.context.dry_run:
            return DispatchResult(decision=decision, serialized=False, sent=False, response=None)
        if not decision.allowed:
            raise EgressRefused(decision)
        serialized, body = await _serialize_payload_async(payload, serializer)
        if not serialized or body is None:
            del payload, serializer
            raise SerializationFailed() from None
        response = await self._transport.send(intent.provider, body)
        return DispatchResult(decision=decision, serialized=True, sent=True, response=response)
