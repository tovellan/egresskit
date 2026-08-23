from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from egresskit import Policy, PolicyEvaluator


def policy_data() -> dict[str, Any]:
    return {
        "schema_version": "1",
        "policy_id": "test_policy",
        "purposes": [{"id": "summarize", "description": "Synthetic summary."}],
        "providers": [
            {
                "id": "processor_a",
                "classifications": ["public", "internal"],
                "purposes": ["summarize"],
                "environments": ["test", "production"],
                "synthetic_only": False,
            },
            {
                "id": "synthetic_processor",
                "classifications": ["internal"],
                "purposes": ["summarize"],
                "environments": ["test"],
                "synthetic_only": True,
            },
        ],
        "rules": [
            {
                "id": "allow_internal_test",
                "effect": "allow",
                "classifications": ["internal"],
                "purposes": ["summarize"],
                "providers": ["processor_a", "synthetic_processor"],
                "environments": ["test"],
                "execution_modes": ["live", "synthetic"],
            },
            {
                "id": "deny_live_processor_a",
                "effect": "deny",
                "classifications": ["internal"],
                "purposes": ["summarize"],
                "providers": ["processor_a"],
                "environments": ["test"],
                "execution_modes": ["live"],
            },
        ],
    }


def make_policy(overrides: Mapping[str, Any] | None = None) -> Policy:
    data = policy_data()
    if overrides:
        data.update(overrides)
    return Policy.model_validate(data)


@pytest.fixture
def evaluator() -> PolicyEvaluator:
    return PolicyEvaluator(make_policy())
