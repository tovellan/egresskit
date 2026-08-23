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
