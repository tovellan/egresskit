.PHONY: audit audit-deps build ci clean-install examples format lint test typecheck

format:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff format --check .
	uv run ruff check .
	uv run python scripts/check_text.py
	uv run python scripts/repository_audit.py

typecheck:
	uv run mypy

test:
	uv run pytest

build:
	uv build

clean-install: build
	./scripts/clean_install.sh

examples:
	uv run python examples/guarded_call.py
	uv run python examples/bound_call.py
	uv run egresskit validate examples/synthetic-policy.yaml
	uv run egresskit lint examples/synthetic-policy.yaml
	uv run egresskit explain examples/synthetic-policy.yaml --classification internal --purpose test_processing --provider mock_processor --environment test --mode synthetic
	uv run egresskit test examples/synthetic-policy.yaml examples/synthetic-tests.yaml

audit-deps:
	uv run pip-audit

audit: lint audit-deps

ci: lint typecheck test clean-install examples audit-deps
