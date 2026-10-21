"""Local prepublication check: reports filenames/object IDs, never credential values."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TOKEN = re.compile(rb'\b(?:sk-(?:or-v1-)?|ghp_|gho_|github_pat_)[A-Za-z0-9_-]{16,}')
ASSIGNMENT = re.compile(rb'(?m)^\s*API_KEY\s*=\s*([^\r\n]+)')


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, check=True).stdout


def private_path(name):
    parts = Path(name).parts
    return any(part == '.env' or part in {'history', '.venv', '__pycache__', 'workspace'} for part in parts)


def check_content(content, location, key):
    if TOKEN.search(content) or (key and key in content):
        raise RuntimeError('Possible credential found in ' + location + '; inspect it locally.')
    for match in ASSIGNMENT.finditer(content):
        value = match.group(1).strip().strip(b'\'"')
        if not value.startswith((b'replace_', b'<', b'your_')):
            raise RuntimeError('Non-placeholder API_KEY assignment in ' + location + '; inspect it locally.')


def main():
    key = os.environ.get('API_KEY', '').encode()
    if not key or key.startswith(b'replace_'):
        raise RuntimeError('Load the local .env to check for the configured key without displaying it.')
    files = git('ls-files', '-z').decode().split('\0')
    files = [name for name in files if name]
    for name in files:
        if private_path(name):
            raise RuntimeError('Private runtime file is tracked: ' + name)
        check_content((ROOT / name).read_bytes(), name, key)
    objects = git('rev-list', '--objects', '--all').decode().splitlines()
    checked = 0
    for entry in objects:
        object_id, _, name = entry.partition(' ')
        if git('cat-file', '-t', object_id).strip() != b'blob':
            continue
        if name and private_path(name):
            raise RuntimeError('Private runtime file appears in Git history: ' + name)
        check_content(git('cat-file', 'blob', object_id), name or object_id, key)
        checked += 1
    summary = {'tracked_files_checked': len(files), 'historical_blobs_checked': checked,
               'configured_api_key_found': False, 'recognized_tokens_found': False,
               'private_runtime_files_tracked': False}
    destination = ROOT / 'validation' / 'publication-scan.json'
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print('PASS: tracked files and Git history contain no configured API key or recognized access token.')
    print('PASS: .env, chat history, workspace files, and virtual environments are not tracked.')
    print(json.dumps(summary))


if __name__ == '__main__':
    try:
        main()
    except RuntimeError as error:
        print('FAIL:', error, file=sys.stderr)
        sys.exit(1)
