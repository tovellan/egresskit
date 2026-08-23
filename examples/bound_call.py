"""Synthetic call through an exact provider destination binding."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from egresskit import BoundGuardedTransport, DestinationBindings, PolicyEvaluator, load_policy
from egresskit.testing import MockDestinationTransport, synthetic_intent

POLICY_PATH = Path(__file__).with_name("synthetic-policy.yaml")


def serialize(value: dict[str, Any]) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode()


def main() -> None:
    raw_transport = MockDestinationTransport()
    guarded = BoundGuardedTransport(
        PolicyEvaluator(load_policy(POLICY_PATH)),
        DestinationBindings({"mock_processor": "https://processor.example.test/v1"}),
        raw_transport,
    )
    result = guarded.dispatch(
        synthetic_intent(),
        {"record_id": "synthetic-001", "content": "fixture-only"},
        serialize,
    )
    print(
        json.dumps(
            {
                "allowed": result.decision.allowed,
                "destination": raw_transport.calls[0][0].url,
                "sent": result.sent,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
