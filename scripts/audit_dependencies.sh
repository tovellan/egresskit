#!/bin/sh
set -eu

audit_cache=$(mktemp -d)
case "$audit_cache" in
  /tmp/*|/private/tmp/*|/var/folders/*) ;;
  *) echo "unexpected temporary directory" >&2; exit 1 ;;
esac
cleanup() {
  rm -rf "$audit_cache"
}
trap cleanup EXIT INT TERM

uv run pip-audit --cache-dir "$audit_cache" --progress-spinner off
