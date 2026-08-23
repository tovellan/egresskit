from __future__ import annotations

import json
import subprocess
import sys


def test_documented_example_executes() -> None:
    completed = subprocess.run(
        [sys.executable, "examples/guarded_call.py"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(completed.stdout) == {
        "allowed": True,
        "sent": True,
        "transport_calls": 1,
    }


def test_bound_example_executes() -> None:
    completed = subprocess.run(
        [sys.executable, "examples/bound_call.py"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(completed.stdout) == {
        "allowed": True,
        "destination": "https://processor.example.test/v1",
        "sent": True,
    }


def test_documented_policy_suite_passes() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "egresskit",
            "test",
            "examples/synthetic-policy.yaml",
            "examples/synthetic-tests.yaml",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    report = json.loads(completed.stdout)
    assert report["passed"] is True
    assert report["total"] == 2
