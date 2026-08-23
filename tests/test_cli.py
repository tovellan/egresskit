from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

from egresskit.cli import EXIT_DENIED, EXIT_INVALID, run

from .conftest import policy_data


def write_policy(tmp_path: Path) -> Path:
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(policy_data()), encoding="utf-8")
    return path


def test_validate_and_schema(tmp_path: Path, capsys: object) -> None:
    path = write_policy(tmp_path)
    assert run(["validate", str(path)]) == 0
    output = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert output == {"policy_id": "test_policy", "schema_version": "1", "status": "valid"}
    assert run(["schema"]) == 0
    assert "schema_version" in json.loads(capsys.readouterr().out)["properties"]  # type: ignore[attr-defined]


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


def test_module_entrypoint() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "egresskit", "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == "egresskit 0.1.0"
