"""Conservative checks for public repository hygiene."""

from __future__ import annotations

import re
import subprocess
import sys
from shutil import which

import yaml
from check_text import repository_files

MAX_FILE_SIZE = 1_000_000
FORBIDDEN_SUFFIXES = {".7z", ".avi", ".gz", ".mov", ".mp3", ".mp4", ".tar", ".wav", ".whl", ".zip"}
LOCAL_PATHS = (
    re.compile("/" + r"Users/[^/\s]+/"),
    re.compile(r"[A-Za-z]:\\" + r"Users\\[^\\\s]+\\"),
)
SECRET_MARKERS = (
    "AK" + "IA",
    "BEGIN " + "PRIVATE KEY",
    "gh" + "p_",
    "gh" + "o_",
    "sk" + "-proj-",
)
ACTION_REFERENCE = re.compile(r"^\s*-\s+uses:\s+([^\s]+)\s*$")
PINNED_ACTION = re.compile(r"^[^@]+@[0-9a-f]{40}$")


def main() -> int:
    failures: list[str] = []
    files = repository_files()
    for path in files:
        size = path.stat().st_size
        if size > MAX_FILE_SIZE:
            failures.append(f"{path}: file is larger than {MAX_FILE_SIZE} bytes")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            failures.append(f"{path}: binary or archive type is not allowed")
        content = path.read_bytes()
        if b"\0" in content:
            failures.append(f"{path}: binary content is not allowed")
            continue
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            failures.append(f"{path}: text is not valid UTF-8")
            continue
        failures.extend(
            f"{path}: local user path found" for pattern in LOCAL_PATHS if pattern.search(text)
        )
        failures.extend(
            f"{path}: credential-like marker found" for marker in SECRET_MARKERS if marker in text
        )
        if path.parts[:2] == (".github", "workflows"):
            try:
                yaml.safe_load(text)
            except yaml.YAMLError:
                failures.append(f"{path}: workflow YAML is invalid")
            for line_number, line in enumerate(text.splitlines(), start=1):
                action = ACTION_REFERENCE.match(line)
                if action and not PINNED_ACTION.fullmatch(action.group(1)):
                    failures.append(f"{path}:{line_number}: action is not pinned to a commit")

    git = which("git")
    if git is None:
        raise RuntimeError("git executable not found")
    has_history = (
        subprocess.run(
            [git, "rev-parse", "--verify", "HEAD"], check=False, capture_output=True
        ).returncode
        == 0
    )
    history = (
        subprocess.run(
            [git, "log", "--format=%B"], check=True, capture_output=True, text=True
        ).stdout
        if has_history
        else ""
    )
    if "\N{EN DASH}" in history or "\N{EM DASH}" in history:
        failures.append("Git history: prohibited Unicode dash")

    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"repository audit passed for {len(files)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
