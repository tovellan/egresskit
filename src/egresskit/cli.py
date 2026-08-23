"""Command line policy validation and decision inspection."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, NoReturn, TextIO

from pydantic import ValidationError

from .errors import EgressKitError
from .explanation import decision_explanation_json_schema, explain_decision
from .models import DataClassification, EgressIntent, ExecutionContext, ExecutionMode
from .policy import PolicyEvaluator, load_policy, policy_json_schema
from .policy_lint import lint_policy, policy_lint_report_json_schema
from .policy_tests import (
    load_policy_test_suite,
    policy_test_suite_json_schema,
    run_policy_tests,
)
from .testing import synthetic_intent

EXIT_INVALID = 2
EXIT_DENIED = 3
EXIT_TEST_FAILURE = 4
EXIT_LINT_FAILURE = 5


class _ArgumentParseError(Exception):
    pass


class _JSONArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise _ArgumentParseError


def _emit(value: Any, *, stream: TextIO | None = None) -> None:
    print(json.dumps(value, indent=2, sort_keys=True), file=stream or sys.stdout)


def _parser() -> argparse.ArgumentParser:
    parser = _JSONArgumentParser(
        prog="egresskit",
        description="Validate and evaluate fail-closed data egress policies.",
    )
    parser.add_argument("--version", action="version", version="egresskit 0.5.4")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate a versioned policy file")
    validate.add_argument("policy", type=Path)

    lint = subparsers.add_parser("lint", help="report ineffective policy declarations")
    lint.add_argument("policy", type=Path)

    decide = subparsers.add_parser("decide", help="evaluate payload-free egress metadata")
    _add_intent_arguments(decide)

    explain = subparsers.add_parser(
        "explain", help="emit a deterministic payload-free decision explanation"
    )
    _add_intent_arguments(explain)

    schema = subparsers.add_parser("schema", help="print a JSON Schema")
    schema.add_argument(
        "--kind",
        choices=("policy", "tests", "lint", "explanation"),
        default="policy",
    )

    policy_test = subparsers.add_parser("test", help="run declarative policy test cases")
    policy_test.add_argument("policy", type=Path)
    policy_test.add_argument("suite", type=Path)

    fixture = subparsers.add_parser("fixture", help="print a synthetic test intent")
    fixture.add_argument("--provider", default="mock_processor")
    fixture.add_argument("--purpose", default="test_processing")
    fixture.add_argument("--environment", default="test")
    fixture.add_argument("--dry-run", action="store_true")
    return parser


def _add_intent_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("policy", type=Path)
    command.add_argument(
        "--classification", required=True, choices=[v.value for v in DataClassification]
    )
    command.add_argument("--purpose", required=True)
    command.add_argument("--provider", required=True)
    command.add_argument("--environment", required=True)
    command.add_argument("--mode", choices=[v.value for v in ExecutionMode], default="live")
    command.add_argument("--dry-run", action="store_true")


def run(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
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
        if args.command == "lint":
            lint_report = lint_policy(load_policy(args.policy))
            _emit(lint_report.model_dump(mode="json"))
            return 0 if lint_report.passed else EXIT_LINT_FAILURE
        if args.command == "schema":
            schemas = {
                "policy": policy_json_schema,
                "tests": policy_test_suite_json_schema,
                "lint": policy_lint_report_json_schema,
                "explanation": decision_explanation_json_schema,
            }
            schema = schemas[args.kind]()
            _emit(schema)
            return 0
        if args.command == "test":
            evaluator = PolicyEvaluator(load_policy(args.policy))
            test_report = run_policy_tests(evaluator, load_policy_test_suite(args.suite))
            _emit(test_report.model_dump(mode="json"))
            return 0 if test_report.passed else EXIT_TEST_FAILURE
        if args.command == "fixture":
            fixture = synthetic_intent(
                provider=args.provider,
                purpose=args.purpose,
                environment=args.environment,
                dry_run=args.dry_run,
            )
            _emit(fixture.model_dump(mode="json"))
            return 0
        if args.command in {"decide", "explain"}:
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
            output = explain_decision(decision) if args.command == "explain" else decision
            _emit(output.model_dump(mode="json"))
            return 0 if decision.allowed else EXIT_DENIED
    except _ArgumentParseError:
        _emit(
            {
                "schema_version": "1",
                "error": {
                    "code": "request_invalid",
                    "message": "command arguments are invalid",
                },
            },
            stream=sys.stderr,
        )
        return EXIT_INVALID
    except EgressKitError as exc:
        _emit(exc.to_dict(), stream=sys.stderr)
        return EXIT_INVALID
    except ValidationError:
        _emit(
            {
                "schema_version": "1",
                "error": {
                    "code": "request_invalid",
                    "message": "request metadata is invalid",
                },
            },
            stream=sys.stderr,
        )
        return EXIT_INVALID
    return EXIT_INVALID


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
