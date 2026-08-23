"""Reject prohibited Unicode dash characters in repository text."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from shutil import which


def repository_files() -> list[Path]:
    git = which("git")
    if git is None:
        raise RuntimeError("git executable not found")
    output = subprocess.run(
        [git, "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        check=True,
        capture_output=True,
    ).stdout
    return [Path(value.decode()) for value in output.split(b"\0") if value]


def main() -> int:
    failures: list[str] = []
    for path in repository_files():
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(content.splitlines(), start=1):
            if "\N{EN DASH}" in line or "\N{EM DASH}" in line:
                failures.append(f"{path}:{line_number}: prohibited Unicode dash")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"text policy passed for {len(repository_files())} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
