from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

from egresskit.cli import EXIT_DENIED, EXIT_INVALID, EXIT_LINT_FAILURE, EXIT_TEST_FAILURE, run

from .conftest import policy_data
from .test_policy_tests import suite_data


def write_policy(tmp_path: Path) -> Path:
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(policy_data()), encoding="utf-8")
    return path


def write_suite(tmp_path: Path, *, passing: bool = True) -> Path:
    data = suite_data()
    if not passing:
        data["cases"][0]["expected_status"] = "deny"  # type: ignore[index]
    path = tmp_path / "suite.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_validate_and_schema(tmp_path: Path, capsys: object) -> None:
    path = write_policy(tmp_path)
    assert run(["validate", str(path)]) == 0
    output = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert output == {"policy_id": "test_policy", "schema_version": "1", "status": "valid"}
    assert run(["schema"]) == 0
    assert "schema_version" in json.loads(capsys.readouterr().out)["properties"]  # type: ignore[attr-defined]
    assert run(["schema", "--kind", "tests"]) == 0
    assert "suite_id" in json.loads(capsys.readouterr().out)["properties"]  # type: ignore[attr-defined]
    assert run(["schema", "--kind", "lint"]) == 0
    assert "diagnostics" in json.loads(capsys.readouterr().out)["properties"]  # type: ignore[attr-defined]
    assert run(["schema", "--kind", "explanation"]) == 0
    assert "reason_codes" in json.loads(capsys.readouterr().out)["properties"]  # type: ignore[attr-defined]


def test_lint_command_passes_and_reports_findings(tmp_path: Path, capsys: object) -> None:
    path = write_policy(tmp_path)
    assert run(["lint", str(path)]) == 0
    report = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert report["passed"] is True

    data = policy_data()
    data["rules"] = []
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    assert run(["lint", str(path)]) == EXIT_LINT_FAILURE
    report = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert report["passed"] is False
    assert report["diagnostic_count"] == 4


def test_fixture(tmp_path: Path, capsys: object) -> None:
    del tmp_path
    assert run(["fixture", "--dry-run"]) == 0
    output = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert output["schema_version"] == "1"
    assert output["context"] == {"dry_run": True, "environment": "test", "mode": "synthetic"}


def test_decide_allow_and_deny(tmp_path: Path, capsys: object) -> None:
    path = write_policy(tmp_path)
    common = [
        "decide",
        str(path),
        "--classification",
        "internal",
        "--purpose",
        "summarize",
        "--provider",
        "processor_a",
        "--environment",
        "test",
    ]
    assert run([*common, "--mode", "synthetic"]) == 0
    output = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert output["schema_version"] == "1"
    assert output["status"] == "allow"
    assert run([*common, "--mode", "live"]) == EXIT_DENIED
    assert json.loads(capsys.readouterr().out)["status"] == "deny"  # type: ignore[attr-defined]


def test_explain_is_deterministic_and_omits_receipt(tmp_path: Path, capsys: object) -> None:
    path = write_policy(tmp_path)
    command = [
        "explain",
        str(path),
        "--classification",
        "internal",
        "--purpose",
        "summarize",
        "--provider",
        "processor_a",
        "--environment",
        "test",
        "--mode",
        "synthetic",
    ]
    assert run(command) == 0
    first = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert run(command) == 0
    second = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert first == second
    assert first["status"] == "allow"
    assert "receipt" not in first
    assert "evaluated_at" not in first


def test_invalid_policy_is_machine_readable(tmp_path: Path, capsys: object) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("schema_version: '2'", encoding="utf-8")
    assert run(["validate", str(path)]) == EXIT_INVALID
    output = json.loads(capsys.readouterr().err)  # type: ignore[attr-defined]
    assert output["error"]["code"] == "policy_invalid"


def test_non_utf8_policy_is_machine_readable(tmp_path: Path, capsys: object) -> None:
    path = tmp_path / "non-utf8.yaml"
    path.write_bytes(b"schema_version: \xff")
    assert run(["validate", str(path)]) == EXIT_INVALID
    output = json.loads(capsys.readouterr().err)  # type: ignore[attr-defined]
    assert output == {
        "schema_version": "1",
        "error": {
            "code": "policy_invalid",
            "message": "policy could not be loaded",
        },
    }


def test_oversized_json_integer_is_machine_readable(tmp_path: Path, capsys: object) -> None:
    path = tmp_path / "oversized.json"
    path.write_text('{"value":' + ("9" * 5_000) + "}", encoding="utf-8")
    assert run(["validate", str(path)]) == EXIT_INVALID
    output = json.loads(capsys.readouterr().err)  # type: ignore[attr-defined]
    assert output["error"] == {
        "code": "policy_invalid",
        "message": "policy could not be loaded",
    }


def test_invalid_request_is_machine_readable(tmp_path: Path, capsys: object) -> None:
    path = write_policy(tmp_path)
    result = run(
        [
            "decide",
            str(path),
            "--classification",
            "internal",
            "--purpose",
            "summarize",
            "--provider",
            "INVALID PROVIDER",
            "--environment",
            "test",
        ]
    )
    assert result == EXIT_INVALID
    output = json.loads(capsys.readouterr().err)  # type: ignore[attr-defined]
    assert output["schema_version"] == "1"
    assert output["error"]["code"] == "request_invalid"


def test_invalid_cli_arguments_are_generic_versioned_json(capsys: object) -> None:
    marker = "protected-argument-marker"
    assert run(["schema", "--kind", marker]) == EXIT_INVALID
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    output = json.loads(captured.err)
    assert captured.out == ""
    assert marker not in captured.err
    assert output == {
        "schema_version": "1",
        "error": {
            "code": "request_invalid",
            "message": "command arguments are invalid",
        },
    }

    assert run([]) == EXIT_INVALID
    output = json.loads(capsys.readouterr().err)  # type: ignore[attr-defined]
    assert output["schema_version"] == "1"
    assert output["error"]["code"] == "request_invalid"


def test_module_argument_error_is_json_without_rejected_value() -> None:
    marker = "protected-subprocess-argument"
    completed = subprocess.run(  # noqa: S603 - exercises untrusted CLI input
        [sys.executable, "-m", "egresskit", "schema", "--kind", marker],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == EXIT_INVALID
    assert completed.stdout == ""
    assert marker not in completed.stderr
    output = json.loads(completed.stderr)
    assert output["schema_version"] == "1"
    assert output["error"]["code"] == "request_invalid"


def test_module_wraps_invalid_explicit_policy_tag_without_echo(tmp_path: Path) -> None:
    marker = "protected-policy-tag-marker"
    raw = yaml.safe_dump(policy_data()).replace(
        "synthetic_only: false", f"synthetic_only: !!int {marker}", 1
    )
    path = tmp_path / "invalid-tag.yaml"
    path.write_text(raw, encoding="utf-8")
    completed = subprocess.run(  # noqa: S603 - exercises untrusted CLI input
        [sys.executable, "-m", "egresskit", "validate", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == EXIT_INVALID
    assert completed.stdout == ""
    assert marker not in completed.stderr
    output = json.loads(completed.stderr)
    assert output["error"]["code"] == "policy_invalid"


def test_module_wraps_invalid_explicit_suite_tag_without_echo(tmp_path: Path) -> None:
    marker = "protected-suite-tag-marker"
    policy = write_policy(tmp_path)
    suite = tmp_path / "invalid-suite-tag.yaml"
    suite.write_text(
        f"schema_version: '1'\nsuite_id: invalid_tag\ncases: !!timestamp {marker}\n",
        encoding="utf-8",
    )
    completed = subprocess.run(  # noqa: S603 - exercises untrusted CLI input
        [sys.executable, "-m", "egresskit", "test", str(policy), str(suite)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == EXIT_INVALID
    assert completed.stdout == ""
    assert marker not in completed.stderr
    output = json.loads(completed.stderr)
    assert output["error"]["code"] == "test_suite_invalid"


def test_module_wraps_deep_json_without_traceback(tmp_path: Path) -> None:
    deep = tmp_path / "deep.json"
    deep.write_text(
        '{"deep":' + "[" * 10_000 + "0" + "]" * 10_000 + "}",
        encoding="utf-8",
    )
    completed = subprocess.run(  # noqa: S603 - exercises untrusted CLI input
        [sys.executable, "-m", "egresskit", "validate", str(deep)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == EXIT_INVALID
    assert completed.stdout == ""
    assert "Traceback" not in completed.stderr
    output = json.loads(completed.stderr)
    assert output["error"]["code"] == "policy_invalid"


def test_policy_test_command_passes_and_reports_mismatch(tmp_path: Path, capsys: object) -> None:
    policy = write_policy(tmp_path)
    passing = write_suite(tmp_path)
    assert run(["test", str(policy), str(passing)]) == 0
    report = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert report["passed"] is True
    assert report["total"] == 2

    failing = write_suite(tmp_path, passing=False)
    assert run(["test", str(policy), str(failing)]) == EXIT_TEST_FAILURE
    report = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert report["passed"] is False
    assert report["failed_count"] == 1


def test_policy_test_command_rejects_unsafe_suite(tmp_path: Path, capsys: object) -> None:
    policy = write_policy(tmp_path)
    suite = tmp_path / "unsafe.yaml"
    suite.write_text(
        "schema_version: '1'\nsuite_id: unsafe\npayload: protected\ncases: []\n",
        encoding="utf-8",
    )
    assert run(["test", str(policy), str(suite)]) == EXIT_INVALID
    error = json.loads(capsys.readouterr().err)  # type: ignore[attr-defined]
    assert error["error"]["code"] == "test_suite_invalid"


def test_module_entrypoint() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "egresskit", "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == "egresskit 0.5.4"
