"""Complete synthetic call with no external network access."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from egresskit import GuardedTransport, PolicyEvaluator, load_policy
from egresskit.testing import MockTransport, synthetic_intent

POLICY_PATH = Path(__file__).with_name("synthetic-policy.yaml")


def serialize(value: dict[str, Any]) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode()


def main() -> None:
    raw_transport = MockTransport()
    guarded = GuardedTransport(PolicyEvaluator(load_policy(POLICY_PATH)), raw_transport)
    result = guarded.dispatch(
        synthetic_intent(),
        {"record_id": "synthetic-001", "content": "fixture-only"},
        serialize,
    )
    print(
        json.dumps(
            {
                "allowed": result.decision.allowed,
                "sent": result.sent,
                "transport_calls": len(raw_transport.calls),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
