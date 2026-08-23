"""Local evaluator microbenchmark. Results vary by machine and are not release claims."""

from __future__ import annotations

import timeit
from pathlib import Path

from egresskit import PolicyEvaluator, load_policy
from egresskit.testing import synthetic_intent

ROOT = Path(__file__).resolve().parents[1]
evaluator = PolicyEvaluator(load_policy(ROOT / "examples/synthetic-policy.yaml"))
intent = synthetic_intent()

if __name__ == "__main__":
    iterations = 10_000
    seconds = timeit.timeit(lambda: evaluator.evaluate(intent), number=iterations)
    print(f"{iterations} evaluations in {seconds:.6f} seconds")
