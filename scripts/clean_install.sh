#!/bin/sh
set -eu

temp_dir=$(mktemp -d)
case "$temp_dir" in
  /tmp/*|/private/tmp/*|/var/folders/*) ;;
  *) echo "unexpected temporary directory" >&2; exit 1 ;;
esac
cleanup() {
  rm -rf "$temp_dir"
}
trap cleanup EXIT INT TERM

uv venv --python 3.10 "$temp_dir/venv"
uv pip install --python "$temp_dir/venv/bin/python" dist/egresskit-0.3.0-py3-none-any.whl
"$temp_dir/venv/bin/egresskit" validate examples/synthetic-policy.yaml >/dev/null
"$temp_dir/venv/bin/egresskit" lint examples/synthetic-policy.yaml >/dev/null
"$temp_dir/venv/bin/egresskit" test examples/synthetic-policy.yaml examples/synthetic-tests.yaml >/dev/null
"$temp_dir/venv/bin/python" examples/guarded_call.py >/dev/null
"$temp_dir/venv/bin/python" examples/bound_call.py >/dev/null
echo "clean installation passed"
