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
    assert json.loads(capsys.readouterr().out)["status"] == "allow"  # type: ignore[attr-defined]
    assert run([*common, "--mode", "live"]) == EXIT_DENIED
    assert json.loads(capsys.readouterr().out)["status"] == "deny"  # type: ignore[attr-defined]


def test_invalid_policy_is_machine_readable(tmp_path: Path, capsys: object) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("schema_version: '2'", encoding="utf-8")
    assert run(["validate", str(path)]) == EXIT_INVALID
    output = json.loads(capsys.readouterr().err)  # type: ignore[attr-defined]
    assert output["error"]["code"] == "policy_invalid"


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
    assert output["error"]["code"] == "request_invalid"


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
    assert completed.stdout.strip() == "egresskit 0.3.0"
