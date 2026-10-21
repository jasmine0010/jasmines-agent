"""Read-only credential and package checks; output contains no secret values."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CLASS = Path.home() / "ai-in-research-homework"
SUBMISSION = "week-3/submissions/jasmine0010"
PATTERN = re.compile(rb'\b(?:(?:sk-(?:or-v1-)?|ghp_|gho_|github_pat_)[A-Za-z0-9_-]{16,}|[0-9]{6,}:[A-Za-z0-9_-]{20,})')


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True).stdout


def private(name):
    return any(part in {".env", "history", ".venv", "__pycache__", "workspace"} for part in Path(name).parts)


def check(data, label, secrets):
    if PATTERN.search(data) or any(value in data for value in secrets):
        raise RuntimeError("Possible credential in " + label + "; inspect locally. No value was printed.")


def inventory(folder):
    return {path.relative_to(folder).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in folder.rglob("*") if path.is_file() and not private(path.relative_to(folder)) and path.suffix != ".pyc"}


def main():
    secrets = [os.environ.get(name, "").encode() for name in ("API_KEY", "TELEGRAM_BOT_TOKEN")]
    if not all(secrets) or any(value.startswith(b"replace_") for value in secrets):
        raise RuntimeError("Load the real settings from the ignored .env locally before this check.")
    counts = {}
    for label, root, scope in (("harness", ROOT, []), ("submission", CLASS, ["--", SUBMISSION])):
        names = set(git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z", *scope).decode().split("\0")) - {""}
        for name in names:
            if private(name):
                raise RuntimeError("Private runtime file selected: " + name)
            check((root / name).read_bytes(), name, secrets)
        counts[label + "_files_checked"] = len(names)
    blobs = 0
    for entry in git(ROOT, "rev-list", "--objects", "--all").decode().splitlines():
        oid, _, name = entry.partition(" ")
        if git(ROOT, "cat-file", "-t", oid).strip() == b"blob":
            if private(name):
                raise RuntimeError("Private runtime path in harness history: " + name)
            check(git(ROOT, "cat-file", "blob", oid), name or oid, secrets)
            blobs += 1
    for name in ("jasmine0010-telegram", "jasmine0010-psp-waves"):
        if inventory(ROOT / "plugins" / name) != inventory(CLASS / SUBMISSION / name):
            raise RuntimeError("Plugin copies differ: " + name)
    if not git(ROOT, "check-ignore", ".env").strip():
        raise RuntimeError(".env must be ignored.")
    receipt = {**counts, "historical_blobs_checked": blobs, "configured_credentials_found": False,
               "recognized_token_patterns_found": False, "plugin_copies_identical": True, "env_ignored": True}
    (ROOT / "validation/week-3-publication-scan.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
