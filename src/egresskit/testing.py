"""Synthetic fixtures and in-memory transports for policy tests."""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import DataClassification, EgressIntent, ExecutionContext, ExecutionMode


def synthetic_intent(
    *,
    provider: str = "mock_processor",
    purpose: str = "test_processing",
    classification: DataClassification = DataClassification.INTERNAL,
    environment: str = "test",
    dry_run: bool = False,
) -> EgressIntent:
    return EgressIntent(
        classification=classification,
        purpose=purpose,
        provider=provider,
        context=ExecutionContext(
            environment=environment,
            mode=ExecutionMode.SYNTHETIC,
            dry_run=dry_run,
        ),
    )


@dataclass
class MockTransport:
    response: bytes = b"synthetic-response"
    calls: list[tuple[str, bytes]] = field(default_factory=list)

    def send(self, provider: str, body: bytes) -> bytes:
        self.calls.append((provider, body))
        return self.response


@dataclass
class MockAsyncTransport:
    response: bytes = b"synthetic-response"
    calls: list[tuple[str, bytes]] = field(default_factory=list)

    async def send(self, provider: str, body: bytes) -> bytes:
        self.calls.append((provider, body))
        return self.response
