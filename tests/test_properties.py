from __future__ import annotations

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from egresskit import EgressRefused, GuardedTransport, PolicyEvaluator
from egresskit.testing import MockTransport

from .conftest import make_policy
from .test_policy import intent


@given(st.binary(max_size=4096))
def test_refusal_never_calls_serializer_for_arbitrary_payload(payload: bytes) -> None:
    raw = MockTransport()
    guarded = GuardedTransport(PolicyEvaluator(make_policy()), raw)
    with pytest.raises(EgressRefused):
        guarded.dispatch(
            intent(mode="live"),
            payload,
            lambda _: pytest.fail("serializer reached for refused payload"),
        )
    assert raw.calls == []


@given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=20, max_size=100))
def test_payload_text_never_appears_in_refusal(random_text: str) -> None:
    payload = f"protected_payload_marker_{random_text}_end"
    guarded = GuardedTransport(PolicyEvaluator(make_policy()), MockTransport())
    with pytest.raises(EgressRefused) as raised:
        guarded.dispatch(intent(mode="live"), payload, str.encode)
    encoded = json.dumps(raised.value.to_dict())
    assert payload not in encoded
