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

package_version=$(uv run python -c \
  'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')
case "$package_version" in
  *[!0-9.]*|.*|*.) echo "package version is invalid" >&2; exit 1 ;;
esac
wheel="dist/egresskit-${package_version}-py3-none-any.whl"
if [ ! -f "$wheel" ]; then
  echo "exact package wheel is missing" >&2
  exit 1
fi

uv venv --python 3.10 "$temp_dir/venv"
uv pip install --python "$temp_dir/venv/bin/python" "$wheel"
installed_version=$(
  "$temp_dir/venv/bin/python" -c 'import egresskit; print(egresskit.__version__)'
)
if [ "$installed_version" != "$package_version" ]; then
  echo "installed package version does not match metadata" >&2
  exit 1
fi
"$temp_dir/venv/bin/egresskit" validate examples/synthetic-policy.yaml >/dev/null
"$temp_dir/venv/bin/egresskit" lint examples/synthetic-policy.yaml >/dev/null
"$temp_dir/venv/bin/egresskit" explain examples/synthetic-policy.yaml \
  --classification internal --purpose test_processing --provider mock_processor \
  --environment test --mode synthetic >/dev/null
"$temp_dir/venv/bin/egresskit" test examples/synthetic-policy.yaml examples/synthetic-tests.yaml >/dev/null
"$temp_dir/venv/bin/python" examples/guarded_call.py >/dev/null
"$temp_dir/venv/bin/python" examples/bound_call.py >/dev/null
uv pip install --python "$temp_dir/venv/bin/python" "${wheel}[httpx]"
"$temp_dir/venv/bin/python" -c "from egresskit.httpx_transport import HTTPXDestinationTransport"
echo "clean installation passed"
