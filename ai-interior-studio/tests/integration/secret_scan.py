"""Scan files for leaked API keys. Run: python -m tests.integration.secret_scan <path> [...]"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sys

PATTERNS = {
    'google_api_key': re.compile(r'AIza[0-9A-Za-z_\-]{35}'),
    'google_aq_key': re.compile(r'\bAQ\.[0-9A-Za-z_\-]{20,}'),
    'openai_key': re.compile(r'\bsk-[A-Za-z0-9_\-]{20,}'),
    'bearer_token': re.compile(r'Bearer\s+[A-Za-z0-9._\-]{20,}'),
}
SKIP_DIRS = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache'}
MAX_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class Finding:
    path: Path
    kind: str
    line: int


def _files(root: Path):
    if root.is_file():
        yield root
        return
    for path in root.rglob('*'):
        if path.is_file() and not SKIP_DIRS.intersection(path.parts) and not path.parent.name.endswith('.egg-info'):
            yield path


def scan(paths, extra_secrets: tuple[str, ...] = ()) -> list[Finding]:
    """Return every match; the secret value itself is never part of a Finding."""
    findings = []
    for root in map(Path, paths):
        for path in _files(root):
            if path.stat().st_size > MAX_BYTES:
                continue
            text = path.read_bytes().decode('utf-8', errors='ignore')
            for number, line in enumerate(text.splitlines(), 1):
                for kind, pattern in PATTERNS.items():
                    if pattern.search(line):
                        findings.append(Finding(path, kind, number))
                for secret in extra_secrets:
                    if secret and secret in line:
                        findings.append(Finding(path, 'known_secret', number))
    return findings


if __name__ == '__main__':
    results = scan(sys.argv[1:] or ['.'])
    for finding in results:
        print(f'{finding.path}:{finding.line}: {finding.kind}')
    print(f'{len(results)} finding(s)')
    sys.exit(1 if results else 0)
