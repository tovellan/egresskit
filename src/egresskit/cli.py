"""Command line policy validation and decision inspection."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO

from pydantic import ValidationError

from .errors import EgressKitError
from .models import DataClassification, EgressIntent, ExecutionContext, ExecutionMode
from .policy import PolicyEvaluator, load_policy, policy_json_schema
from .testing import synthetic_intent

EXIT_INVALID = 2
EXIT_DENIED = 3


def _emit(value: Any, *, stream: TextIO | None = None) -> None:
    print(json.dumps(value, indent=2, sort_keys=True), file=stream or sys.stdout)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="egresskit",
        description="Validate and evaluate fail-closed data egress policies.",
    )
    parser.add_argument("--version", action="version", version="egresskit 0.1.0")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate a versioned policy file")
    validate.add_argument("policy", type=Path)

    decide = subparsers.add_parser("decide", help="evaluate payload-free egress metadata")
    decide.add_argument("policy", type=Path)
    decide.add_argument(
        "--classification", required=True, choices=[v.value for v in DataClassification]
    )
    decide.add_argument("--purpose", required=True)
    decide.add_argument("--provider", required=True)
    decide.add_argument("--environment", required=True)
    decide.add_argument("--mode", choices=[v.value for v in ExecutionMode], default="live")
    decide.add_argument("--dry-run", action="store_true")

    subparsers.add_parser("schema", help="print the policy JSON Schema")

    fixture = subparsers.add_parser("fixture", help="print a synthetic test intent")
    fixture.add_argument("--provider", default="mock_processor")
    fixture.add_argument("--purpose", default="test_processing")
    fixture.add_argument("--environment", default="test")
    fixture.add_argument("--dry-run", action="store_true")
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            policy = load_policy(args.policy)
            _emit(
                {
                    "policy_id": policy.policy_id,
                    "schema_version": policy.schema_version,
                    "status": "valid",
                }
            )
            return 0
        if args.command == "schema":
            _emit(policy_json_schema())
            return 0
        if args.command == "fixture":
            fixture = synthetic_intent(
                provider=args.provider,
                purpose=args.purpose,
                environment=args.environment,
                dry_run=args.dry_run,
            )
            _emit(fixture.model_dump(mode="json"))
            return 0
        if args.command == "decide":
            intent = EgressIntent(
                classification=DataClassification(args.classification),
                purpose=args.purpose,
                provider=args.provider,
                context=ExecutionContext(
                    environment=args.environment,
                    mode=ExecutionMode(args.mode),
                    dry_run=args.dry_run,
                ),
            )
            decision = PolicyEvaluator(load_policy(args.policy)).evaluate(intent)
            _emit(decision.model_dump(mode="json"))
            return 0 if decision.allowed else EXIT_DENIED
    except EgressKitError as exc:
        _emit(exc.to_dict(), stream=sys.stderr)
        return EXIT_INVALID
    except ValidationError:
        _emit(
            {"error": {"code": "request_invalid", "message": "request metadata is invalid"}},
            stream=sys.stderr,
        )
        return EXIT_INVALID
    return EXIT_INVALID


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
