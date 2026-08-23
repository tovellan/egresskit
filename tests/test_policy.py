from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from egresskit import (
    DataClassification,
    DecisionStatus,
    EgressIntent,
    ExecutionContext,
    ExecutionMode,
    Policy,
    PolicyEvaluator,
    PolicyLoadError,
    ReasonCode,
    load_policy,
    policy_digest,
    policy_json_schema,
)

from .conftest import make_policy, policy_data


def intent(
    *,
    classification: str = "internal",
    purpose: str = "summarize",
    provider: str = "processor_a",
    environment: str = "test",
    mode: str = "synthetic",
    dry_run: bool = False,
) -> EgressIntent:
    return EgressIntent.model_validate(
        {
            "classification": classification,
            "purpose": purpose,
            "provider": provider,
            "context": {"environment": environment, "mode": mode, "dry_run": dry_run},
        }
    )


def test_loads_yaml_and_json(tmp_path: Path) -> None:
    yaml_path = tmp_path / "policy.yaml"
    yaml_path.write_text(yaml.safe_dump(policy_data()), encoding="utf-8")
    json_path = tmp_path / "policy.json"
    json_path.write_text(json.dumps(policy_data()), encoding="utf-8")
    assert load_policy(yaml_path) == load_policy(json_path)


@pytest.mark.parametrize(
    ("content", "suffix", "code"),
    [
        ("[]", ".json", "policy_root_invalid"),
        ("{", ".json", "policy_invalid"),
        ('{"policy_id": NaN}', ".json", "policy_invalid"),
        ("!!python/object:bad", ".yaml", "policy_invalid"),
        ("? [a, b]\n: value", ".yaml", "policy_invalid"),
    ],
)
def test_load_errors_are_safe(tmp_path: Path, content: str, suffix: str, code: str) -> None:
    path = tmp_path / f"policy{suffix}"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(PolicyLoadError) as raised:
        load_policy(path)
    assert raised.value.code == code
    assert content not in raised.value.message
    assert raised.value.to_dict()["error"]["code"] == code


def test_missing_policy_is_wrapped(tmp_path: Path) -> None:
    with pytest.raises(PolicyLoadError, match="could not be loaded"):
        load_policy(tmp_path / "missing.yaml")


def test_non_utf8_policy_is_wrapped(tmp_path: Path) -> None:
    path = tmp_path / "policy.yaml"
    path.write_bytes(b"schema_version: \xff")
    with pytest.raises(PolicyLoadError) as raised:
        load_policy(path)
    assert raised.value.code == "policy_invalid"


def test_deep_json_policy_is_wrapped(tmp_path: Path) -> None:
    path = tmp_path / "deep.json"
    path.write_text(
        '{"deep":' + "[" * 10_000 + "0" + "]" * 10_000 + "}",
        encoding="utf-8",
    )
    with pytest.raises(PolicyLoadError) as raised:
        load_policy(path)
    assert raised.value.code == "policy_invalid"
    assert "\\xff" not in raised.value.message


@pytest.mark.parametrize(
    ("suffix", "content"),
    [
        (
            ".json",
            '{"schema_version":"1","policy_id":"first","policy_id":"second"}',
        ),
        (
            ".json",
            '{"schema_version":"1","policy_id":"test","nested":{"effect":"deny","effect":"allow"}}',
        ),
        (
            ".yaml",
            'schema_version: "1"\npolicy_id: first\npolicy_id: second\n',
        ),
        (
            ".yaml",
            'schema_version: "1"\npolicy_id: test\nnested:\n  effect: deny\n  effect: allow\n',
        ),
        (
            ".yaml",
            'schema_version: "1"\nfirst: &first {a: 1}\nsecond: &second {b: 2}\n'
            "nested:\n  <<: *first\n  <<: *second\n",
        ),
        (
            ".yaml",
            'schema_version: "1"\nnested:\n  <<:\n    <<: &first {a: 1}\n    <<: &second {b: 2}\n',
        ),
        (
            ".yaml",
            'schema_version: "1"\ndefaults: &defaults {effect: deny}\n'
            "nested:\n  <<: *defaults\n  effect: allow\n",
        ),
    ],
)
def test_policy_loader_rejects_duplicate_keys(tmp_path: Path, suffix: str, content: str) -> None:
    path = tmp_path / f"policy{suffix}"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(PolicyLoadError) as raised:
        load_policy(path)
    assert raised.value.code == "policy_invalid"
    assert "duplicate" in str(raised.value.__cause__).lower()
    assert content not in raised.value.message


def test_policy_loader_wraps_oversized_json_integer(tmp_path: Path) -> None:
    content = '{"value":' + ("9" * 5_000) + "}"
    path = tmp_path / "policy.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(PolicyLoadError) as raised:
        load_policy(path)
    assert raised.value.code == "policy_invalid"
    assert content not in raised.value.message


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: data.update(schema_version="2"),
        lambda data: data.update(unexpected=True),
        lambda data: data.update(purposes=data["purposes"] * 2),
        lambda data: data.update(providers=data["providers"] * 2),
        lambda data: data.update(rules=data["rules"] * 2),
        lambda data: data["providers"][0].update(purposes=["unknown"]),
        lambda data: data["rules"][0].update(purposes=["unknown"]),
        lambda data: data["rules"][0].update(providers=["unknown"]),
    ],
)
def test_policy_rejects_invalid_structure(mutation: object) -> None:
    data = policy_data()
    mutation(data)  # type: ignore[operator]
    with pytest.raises(ValidationError):
        Policy.model_validate(data)


def test_explicit_allow() -> None:
    decision = PolicyEvaluator(make_policy()).evaluate(intent())
    assert decision.status is DecisionStatus.ALLOW
    assert decision.reason_codes == (ReasonCode.ALLOWED_BY_RULE,)
    assert decision.matched_rule_ids == ("allow_internal_test",)
    assert decision.receipt.status is decision.status
    assert decision.receipt.policy_digest == policy_digest(make_policy())


def test_deny_overrides_allow() -> None:
    decision = PolicyEvaluator(make_policy()).evaluate(intent(mode="live"))
    assert not decision.allowed
    assert decision.reason_codes == (ReasonCode.EXPLICIT_DENY,)
    assert decision.matched_rule_ids == ("allow_internal_test", "deny_live_processor_a")


@pytest.mark.parametrize(
    ("intent_overrides", "reason"),
    [
        ({"provider": "missing"}, ReasonCode.UNKNOWN_PROVIDER),
        ({"purpose": "missing"}, ReasonCode.UNKNOWN_PURPOSE),
        ({"classification": "restricted"}, ReasonCode.CLASSIFICATION_NOT_SUPPORTED),
        ({"environment": "staging"}, ReasonCode.ENVIRONMENT_NOT_SUPPORTED),
        ({"provider": "synthetic_processor", "mode": "live"}, ReasonCode.SYNTHETIC_ONLY_PROVIDER),
    ],
)
def test_capability_failures(intent_overrides: dict[str, str], reason: ReasonCode) -> None:
    decision = PolicyEvaluator(make_policy()).evaluate(
        intent(**intent_overrides)  # type: ignore[arg-type]
    )
    assert not decision.allowed
    assert reason in decision.reason_codes


def test_provider_purpose_ceiling() -> None:
    data = policy_data()
    data["purposes"].append({"id": "embed", "description": "Synthetic embedding."})
    data["rules"].append(
        {
            **data["rules"][0],
            "id": "allow_embed",
            "purposes": ["embed"],
        }
    )
    decision = PolicyEvaluator(Policy.model_validate(data)).evaluate(intent(purpose="embed"))
    assert decision.reason_codes == (ReasonCode.PURPOSE_NOT_SUPPORTED,)


def test_no_matching_allow_fails_closed() -> None:
    decision = PolicyEvaluator(make_policy()).evaluate(
        intent(classification="public", environment="production")
    )
    assert decision.reason_codes == (ReasonCode.NO_MATCHING_ALLOW,)


def test_receipt_is_unique_but_payload_free() -> None:
    evaluator = PolicyEvaluator(make_policy())
    first = evaluator.evaluate(intent(dry_run=True)).receipt
    second = evaluator.evaluate(intent(dry_run=True)).receipt
    encoded = json.dumps(first.model_dump(mode="json"))
    assert first.receipt_id != second.receipt_id
    assert first.dry_run
    for forbidden in ("payload", "endpoint", "body", "secret-value"):
        assert forbidden not in encoded.lower()


def test_digest_ignores_input_order_for_sets() -> None:
    first = make_policy()
    data = policy_data()
    data["providers"][0]["classifications"].reverse()
    assert policy_digest(first) == policy_digest(Policy.model_validate(data))


def test_schema_is_versioned_and_forbids_extra_fields() -> None:
    schema = policy_json_schema()
    assert schema["properties"]["schema_version"]["const"] == "1"
    assert schema["additionalProperties"] is False


def test_intent_and_decision_contracts_are_versioned() -> None:
    request = intent()
    decision = PolicyEvaluator(make_policy()).evaluate(request)
    assert request.schema_version == "1"
    assert decision.schema_version == "1"
    assert request.model_dump(mode="json")["schema_version"] == "1"
    assert decision.model_dump(mode="json")["schema_version"] == "1"


@pytest.mark.parametrize("value", ["false", "off", 0, 1])
def test_security_booleans_reject_coercion(value: object) -> None:
    policy = policy_data()
    policy["providers"][0]["synthetic_only"] = value
    with pytest.raises(ValidationError):
        Policy.model_validate(policy)

    request = intent().model_dump(mode="python")
    request["context"]["dry_run"] = value
    with pytest.raises(ValidationError):
        EgressIntent.model_validate(request)


@pytest.mark.parametrize("token", ["no", "off", "yes", "on"])
def test_policy_loader_rejects_legacy_yaml_boolean_tokens(tmp_path: Path, token: str) -> None:
    raw = yaml.safe_dump(policy_data()).replace(
        "synthetic_only: false", f"synthetic_only: {token}", 1
    )
    path = tmp_path / "policy.yaml"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(PolicyLoadError) as raised:
        load_policy(path)
    assert raised.value.code == "policy_invalid"


@pytest.mark.parametrize(
    "tagged_value",
    [
        "!!bool yes",
        "!!bool no",
        "!!bool on",
        "!!bool off",
        "!!bool protected-marker",
        "!!int protected-marker",
        "!!float protected-marker",
        "!!timestamp protected-marker",
    ],
)
def test_policy_loader_wraps_invalid_explicit_yaml_tags(
    tmp_path: Path,
    tagged_value: str,
) -> None:
    raw = yaml.safe_dump(policy_data()).replace(
        "synthetic_only: false", f"synthetic_only: {tagged_value}", 1
    )
    path = tmp_path / "policy.yaml"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(PolicyLoadError) as raised:
        load_policy(path)
    assert raised.value.code == "policy_invalid"


def test_policy_loader_accepts_explicit_true_and_false_booleans(tmp_path: Path) -> None:
    raw = yaml.safe_dump(policy_data()).replace(
        "synthetic_only: false", "synthetic_only: !!bool false", 1
    )
    raw = raw.replace("synthetic_only: true", "synthetic_only: !!bool true", 1)
    path = tmp_path / "policy.yaml"
    path.write_text(raw, encoding="utf-8")
    policy = load_policy(path)
    assert not policy.providers[0].synthetic_only
    assert policy.providers[1].synthetic_only


def test_evaluator_policy_is_read_only() -> None:
    original = make_policy()
    evaluator = PolicyEvaluator(original)
    replacement_data = policy_data()
    replacement_data["policy_id"] = "replacement_policy"
    replacement = Policy.model_validate(replacement_data)
    with pytest.raises(AttributeError):
        evaluator.policy = replacement  # type: ignore[misc]
    assert evaluator.policy is original
    assert evaluator.evaluate(intent()).receipt.policy_digest == policy_digest(original)


def test_typed_enum_construction() -> None:
    context = ExecutionContext(environment="test", mode=ExecutionMode.SYNTHETIC)
    request = EgressIntent(
        classification=DataClassification.INTERNAL,
        purpose="summarize",
        provider="processor_a",
        context=context,
    )
    assert request.context.mode is ExecutionMode.SYNTHETIC
