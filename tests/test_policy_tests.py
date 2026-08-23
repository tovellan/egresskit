from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from egresskit import (
    PolicyEvaluator,
    PolicyTestSuite,
    load_policy_test_suite,
    policy_test_suite_json_schema,
    run_policy_tests,
)
from egresskit import (
    TestSuiteLoadError as SuiteLoadError,
)

from .conftest import make_policy


def suite_data() -> dict[str, object]:
    return {
        "schema_version": "1",
        "suite_id": "synthetic_contract",
        "cases": [
            {
                "id": "allowed_case",
                "intent": {
                    "classification": "internal",
                    "purpose": "summarize",
                    "provider": "processor_a",
                    "context": {
                        "environment": "test",
                        "mode": "synthetic",
                        "dry_run": True,
                    },
                },
                "expected_status": "allow",
                "expected_reason_codes": ["allowed_by_rule"],
            },
            {
                "id": "denied_case",
                "intent": {
                    "classification": "restricted",
                    "purpose": "summarize",
                    "provider": "processor_a",
                    "context": {
                        "environment": "test",
                        "mode": "synthetic",
                        "dry_run": True,
                    },
                },
                "expected_status": "deny",
                "expected_reason_codes": ["classification_not_supported"],
            },
        ],
    }


def test_loads_yaml_and_json(tmp_path: Path) -> None:
    yaml_path = tmp_path / "suite.yaml"
    yaml_path.write_text(yaml.safe_dump(suite_data()), encoding="utf-8")
    json_path = tmp_path / "suite.json"
    json_path.write_text(json.dumps(suite_data()), encoding="utf-8")
    assert load_policy_test_suite(yaml_path) == load_policy_test_suite(json_path)


@pytest.mark.parametrize(
    ("content", "suffix", "code"),
    [
        ("[]", ".json", "test_suite_root_invalid"),
        ("{", ".json", "test_suite_invalid"),
        ("!!python/object:bad", ".yaml", "test_suite_invalid"),
    ],
)
def test_load_errors_are_safe(tmp_path: Path, content: str, suffix: str, code: str) -> None:
    path = tmp_path / f"suite{suffix}"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(SuiteLoadError) as raised:
        load_policy_test_suite(path)
    assert raised.value.code == code
    assert content not in raised.value.message


def test_missing_suite_is_wrapped(tmp_path: Path) -> None:
    with pytest.raises(SuiteLoadError, match="could not be loaded"):
        load_policy_test_suite(tmp_path / "missing.yaml")


def test_non_utf8_suite_is_wrapped(tmp_path: Path) -> None:
    path = tmp_path / "suite.yaml"
    path.write_bytes(b"schema_version: \xff")
    with pytest.raises(SuiteLoadError) as raised:
        load_policy_test_suite(path)
    assert raised.value.code == "test_suite_invalid"


def test_deep_json_suite_is_wrapped(tmp_path: Path) -> None:
    path = tmp_path / "deep.json"
    path.write_text(
        '{"deep":' + "[" * 10_000 + "0" + "]" * 10_000 + "}",
        encoding="utf-8",
    )
    with pytest.raises(SuiteLoadError) as raised:
        load_policy_test_suite(path)
    assert raised.value.code == "test_suite_invalid"
    assert "\\xff" not in raised.value.message


@pytest.mark.parametrize(
    ("suffix", "content"),
    [
        (
            ".json",
            '{"schema_version":"1","suite_id":"first","suite_id":"second"}',
        ),
        (
            ".json",
            '{"schema_version":"1","suite_id":"test","case":{"expected_status":"deny",'
            '"expected_status":"allow"}}',
        ),
        (
            ".yaml",
            'schema_version: "1"\nsuite_id: first\nsuite_id: second\n',
        ),
        (
            ".yaml",
            'schema_version: "1"\nsuite_id: test\ncase:\n  expected_status: deny\n'
            "  expected_status: allow\n",
        ),
        (
            ".yaml",
            'schema_version: "1"\nfirst: &first {a: 1}\nsecond: &second {b: 2}\n'
            "case:\n  <<: *first\n  <<: *second\n",
        ),
        (
            ".yaml",
            'schema_version: "1"\ncase:\n  <<:\n    <<: &first {a: 1}\n    <<: &second {b: 2}\n',
        ),
    ],
)
def test_suite_loader_rejects_duplicate_keys(tmp_path: Path, suffix: str, content: str) -> None:
    path = tmp_path / f"suite{suffix}"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(SuiteLoadError) as raised:
        load_policy_test_suite(path)
    assert raised.value.code == "test_suite_invalid"
    assert "duplicate" in str(raised.value.__cause__).lower()
    assert content not in raised.value.message


def test_suite_loader_wraps_oversized_json_integer(tmp_path: Path) -> None:
    content = '{"value":' + ("9" * 5_000) + "}"
    path = tmp_path / "suite.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(SuiteLoadError) as raised:
        load_policy_test_suite(path)
    assert raised.value.code == "test_suite_invalid"
    assert content not in raised.value.message


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: data.update(schema_version="2"),
        lambda data: data.update(payload="protected"),
        lambda data: data.update(cases=data["cases"] * 2),
        lambda data: data["cases"][0]["intent"].update(payload="protected"),
        lambda data: data["cases"][0]["intent"]["context"].update(mode="live"),
        lambda data: data["cases"][0]["intent"]["context"].update(dry_run=False),
        lambda data: data["cases"][0].update(
            expected_reason_codes=["allowed_by_rule", "allowed_by_rule"]
        ),
    ],
)
def test_suite_rejects_unsafe_or_invalid_structure(mutation: object) -> None:
    data = suite_data()
    mutation(data)  # type: ignore[operator]
    with pytest.raises(ValidationError):
        PolicyTestSuite.model_validate(data)


def test_runner_passes_and_is_deterministic() -> None:
    evaluator = PolicyEvaluator(make_policy())
    suite = PolicyTestSuite.model_validate(suite_data())
    first = run_policy_tests(evaluator, suite)
    second = run_policy_tests(evaluator, suite)
    assert first == second
    assert first.passed
    assert first.total == 2
    assert first.passed_count == 2
    assert first.failed_count == 0
    encoded = json.dumps(first.model_dump(mode="json"))
    for forbidden in ("payload", "receipt", "endpoint", "evaluated_at"):
        assert forbidden not in encoded


def test_runner_reports_mismatch_without_raising() -> None:
    data = suite_data()
    data["cases"][0]["expected_status"] = "deny"  # type: ignore[index]
    report = run_policy_tests(PolicyEvaluator(make_policy()), PolicyTestSuite.model_validate(data))
    assert not report.passed
    assert report.passed_count == 1
    assert report.failed_count == 1
    assert not report.cases[0].passed


def test_expected_reasons_are_canonicalized() -> None:
    data = suite_data()
    data["cases"][1]["expected_reason_codes"] = [  # type: ignore[index]
        "unknown_provider",
        "classification_not_supported",
    ]
    suite = PolicyTestSuite.model_validate(data)
    assert [reason.value for reason in suite.cases[1].expected_reason_codes or ()] == [
        "classification_not_supported",
        "unknown_provider",
    ]


def test_test_suite_schema_is_versioned_and_strict() -> None:
    schema = policy_test_suite_json_schema()
    assert schema["properties"]["schema_version"]["const"] == "1"
    assert schema["additionalProperties"] is False
