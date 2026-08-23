"""Provider destination bindings and pre-serialization enforcement."""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Generic, Protocol, TypeVar
from urllib.parse import urlsplit

from .errors import DestinationRefused, EgressRefused, SerializationFailed
from .models import IDENTIFIER_PATTERN, Decision, EgressIntent
from .policy import PolicyEvaluator
from .transport import DispatchResult, _serialize_payload, _serialize_payload_async

PayloadT = TypeVar("PayloadT")
ResponseT = TypeVar("ResponseT", covariant=True)

_IDENTIFIER = re.compile(IDENTIFIER_PATTERN)
_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_LEGACY_IPV4 = re.compile(r"^(?:0x[0-9a-f]+|[0-9]+)(?:\.(?:0x[0-9a-f]+|[0-9]+)){0,3}$")
_PATH = re.compile(r"^/[A-Za-z0-9._~!$&'()*+,;=:@/-]*$")


@dataclass(frozen=True, slots=True)
class Destination:
    """Canonical HTTPS destination without credentials, query, or fragment."""

    host: str
    port: int = 443
    path: str = "/"

    def __post_init__(self) -> None:
        if not isinstance(self.host, str):
            raise ValueError("destination host is invalid")
        if self._canonical_host(self.host) != self.host:
            raise ValueError("destination host must be canonical")
        if (
            not isinstance(self.port, int)
            or isinstance(self.port, bool)
            or not 1 <= self.port <= 65535
        ):
            raise ValueError("destination port is invalid")
        if not isinstance(self.path, str):
            raise ValueError("destination path is invalid")
        self._validate_path(self.path)

    @classmethod
    def from_url(cls, value: str) -> Destination:
        if (
            not isinstance(value, str)
            or not value.isascii()
            or value != value.strip()
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise ValueError("destination URL is invalid")
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError as exc:
            raise ValueError("destination URL is invalid") from exc
        if parsed.scheme.lower() != "https":
            raise ValueError("destination scheme must be https")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("destination must not contain user information")
        if "?" in value or "#" in value:
            raise ValueError("destination must not contain a query or fragment")
        if parsed.hostname is None:
            raise ValueError("destination host is required")
        authority = parsed.netloc.rsplit("@", 1)[-1]
        if authority.endswith(":"):
            raise ValueError("destination port is invalid")
        if authority.startswith("["):
            try:
                ipaddress.IPv6Address(parsed.hostname)
            except ValueError:
                raise ValueError("destination host is invalid") from None
        host = cls._canonical_host(parsed.hostname)
        path = parsed.path or "/"
        cls._validate_path(path)
        return cls(host=host, port=443 if port is None else port, path=path)

    @staticmethod
    def _canonical_host(value: str) -> str:
        if not value.isascii():
            raise ValueError("destination host must be ASCII")
        host = value.lower()
        if host.endswith(".") or "%" in host:
            raise ValueError("destination host must be canonical")
        try:
            return ipaddress.ip_address(host).compressed
        except ValueError:
            if all(character in "0123456789." for character in host) or _LEGACY_IPV4.fullmatch(
                host
            ):
                raise ValueError("destination host is ambiguous") from None
            if len(host) > 253 or not all(_DNS_LABEL.fullmatch(label) for label in host.split(".")):
                raise ValueError("destination host is invalid") from None
            return host

    @staticmethod
    def _validate_path(path: str) -> None:
        if not _PATH.fullmatch(path) or "%" in path or "//" in path:
            raise ValueError("destination path must be canonical")
        if any(segment in {".", ".."} for segment in path.split("/")):
            raise ValueError("destination path must not contain dot segments")

    @property
    def url(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        authority = host if self.port == 443 else f"{host}:{self.port}"
        return f"https://{authority}{self.path}"


class DestinationBindings:
    """Immutable exact bindings from policy provider identifiers to destinations."""

    def __init__(self, bindings: Mapping[str, str | Destination]) -> None:
        normalized: dict[str, Destination] = {}
        for provider, destination in bindings.items():
            if (
                not isinstance(provider, str)
                or not _IDENTIFIER.fullmatch(provider)
                or len(provider) > 128
            ):
                raise ValueError("provider identifier is invalid")
            normalized[provider] = (
                destination
                if isinstance(destination, Destination)
                else Destination.from_url(destination)
            )
        if not normalized:
            raise ValueError("at least one destination binding is required")
        self._bindings = MappingProxyType(normalized)

    def resolve(self, provider: str) -> Destination:
        try:
            return self._bindings[provider]
        except KeyError:
            raise DestinationRefused(provider=provider, reason="provider_unbound") from None

    def require(self, provider: str, destination: str | Destination) -> Destination:
        expected = self.resolve(provider)
        actual = (
            destination
            if isinstance(destination, Destination)
            else Destination.from_url(destination)
        )
        if actual != expected:
            raise DestinationRefused(provider=provider, reason="destination_mismatch")
        return expected


class DestinationTransport(Protocol[ResponseT]):
    def send(self, destination: Destination, body: bytes) -> ResponseT: ...


class AsyncDestinationTransport(Protocol[ResponseT]):
    async def send(self, destination: Destination, body: bytes) -> ResponseT: ...


class BoundGuardedTransport(Generic[ResponseT]):
    """Authorize policy and destination binding before synchronous serialization."""

    def __init__(
        self,
        evaluator: PolicyEvaluator,
        bindings: DestinationBindings,
        transport: DestinationTransport[ResponseT],
    ) -> None:
        self._evaluator = evaluator
        self._bindings = bindings
        self._transport = transport

    def dispatch(
        self,
        intent: EgressIntent,
        payload: PayloadT,
        serializer: Callable[[PayloadT], bytes],
    ) -> DispatchResult[ResponseT]:
        decision, destination = self._preflight(intent)
        if intent.context.dry_run:
            return DispatchResult(decision=decision, serialized=False, sent=False, response=None)
        if destination is None:
            raise EgressRefused(decision)
        serialized, body = _serialize_payload(payload, serializer)
        if not serialized or body is None:
            del payload, serializer
            raise SerializationFailed() from None
        response = self._transport.send(destination, body)
        return DispatchResult(decision=decision, serialized=True, sent=True, response=response)

    def _preflight(self, intent: EgressIntent) -> tuple[Decision, Destination | None]:
        decision = self._evaluator.evaluate(intent)
        if not decision.allowed:
            if intent.context.dry_run:
                return decision, None
            raise EgressRefused(decision)
        return decision, self._bindings.resolve(intent.provider)


class BoundGuardedAsyncTransport(Generic[ResponseT]):
    """Authorize policy and destination binding before asynchronous serialization."""

    def __init__(
        self,
        evaluator: PolicyEvaluator,
        bindings: DestinationBindings,
        transport: AsyncDestinationTransport[ResponseT],
    ) -> None:
        self._evaluator = evaluator
        self._bindings = bindings
        self._transport = transport

    async def dispatch(
        self,
        intent: EgressIntent,
        payload: PayloadT,
        serializer: Callable[[PayloadT], bytes] | Callable[[PayloadT], Awaitable[bytes]],
    ) -> DispatchResult[ResponseT]:
        decision, destination = self._preflight(intent)
        if intent.context.dry_run:
            return DispatchResult(decision=decision, serialized=False, sent=False, response=None)
        if destination is None:
            raise EgressRefused(decision)
        serialized, body = await _serialize_payload_async(payload, serializer)
        if not serialized or body is None:
            del payload, serializer
            raise SerializationFailed() from None
        response = await self._transport.send(destination, body)
        return DispatchResult(decision=decision, serialized=True, sent=True, response=response)

    def _preflight(self, intent: EgressIntent) -> tuple[Decision, Destination | None]:
        decision = self._evaluator.evaluate(intent)
        if not decision.allowed:
            if intent.context.dry_run:
                return decision, None
            raise EgressRefused(decision)
        return decision, self._bindings.resolve(intent.provider)
