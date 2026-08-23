"""Provider destination bindings and pre-serialization enforcement."""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Generic, Protocol, TypeVar
from urllib.parse import SplitResult, urlsplit

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


def _validate_provider_identifier(provider: object) -> str:
    if type(provider) is not str or len(provider) > 128 or not _IDENTIFIER.fullmatch(provider):
        raise ValueError("provider identifier is invalid")
    return provider


def _split_destination_url(value: str) -> tuple[SplitResult, int | None] | None:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    return parsed, port


@dataclass(frozen=True, slots=True)
class Destination:
    """Canonical HTTPS destination without credentials, query, or fragment."""

    host: str
    port: int = 443
    path: str = "/"

    def __post_init__(self) -> None:
        if type(self) is not Destination:
            raise ValueError("destination type is invalid")
        if type(self.host) is not str:
            raise ValueError("destination host is invalid")
        if self._canonical_host(self.host) != self.host:
            raise ValueError("destination host must be canonical")
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError("destination port is invalid")
        if type(self.path) is not str:
            raise ValueError("destination path is invalid")
        self._validate_path(self.path)

    @classmethod
    def from_url(cls, value: str) -> Destination:
        if cls is not Destination:
            raise ValueError("destination type is invalid")
        if (
            type(value) is not str
            or not value.isascii()
            or value != value.strip()
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise ValueError("destination URL is invalid")
        parsed_url = _split_destination_url(value)
        if parsed_url is None:
            raise ValueError("destination URL is invalid") from None
        parsed, port = parsed_url
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


def _validate_destination_binding(destination: object) -> Destination:
    if type(destination) is Destination:
        return destination
    if type(destination) is str:
        return Destination.from_url(destination)
    raise ValueError("destination binding is invalid")


class DestinationBindings:
    """Immutable exact bindings from policy provider identifiers to destinations."""

    def __init__(self, bindings: Mapping[str, str | Destination]) -> None:
        normalized: dict[str, Destination] = {}
        for provider, destination in bindings.items():
            validated_provider = _validate_provider_identifier(provider)
            normalized[validated_provider] = _validate_destination_binding(destination)
        if not normalized:
            raise ValueError("at least one destination binding is required")
        self._bindings = MappingProxyType(normalized)

    def resolve(self, provider: str) -> Destination:
        validated_provider = _validate_provider_identifier(provider)
        destination = self._bindings.get(validated_provider)
        if destination is None:
            raise DestinationRefused(provider=None, reason="provider_unbound") from None
        return destination

    def require(self, provider: str, destination: str | Destination) -> Destination:
        validated_provider = _validate_provider_identifier(provider)
        expected = self.resolve(validated_provider)
        actual = _validate_destination_binding(destination)
        if actual != expected:
            raise DestinationRefused(provider=validated_provider, reason="destination_mismatch")
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
