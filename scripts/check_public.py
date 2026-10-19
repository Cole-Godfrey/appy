#!/usr/bin/env python3
"""Check tracked files for private paths, credentials, and broken local doc links."""
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = {'.env', 'INFORMATION.md', 'QUESTIONS.md', 'NEXT-STEPS.md',
           'CAREER-FAIR-COMPANIES.md', 'prompt.md'}
PRIVATE_DIRS = {'private', 'tmp', 'evidence', 'oauth-info', '.venv', 'venv', '__pycache__'}
SUFFIXES = {'.pdf', '.docx', '.xlsx', '.csv', '.pem', '.key', '.db', '.log'}
EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})')
MAIL_DOMAINS = {'example.com', 'example.org', 'example.net', 'users.noreply.github.com'}
PATTERNS = {
    'credential-like value': re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AIza[A-Za-z0-9_-]{30,}|sk-[A-Za-z0-9_-]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)'),
    'absolute user path': re.compile(r'/(?:Users|home)/[A-Za-z0-9_.-]+/'),
    'private Notion or Simplify profile link': re.compile(r'(?:collection://(?!11111111-1111-4111-8111-111111111111)[0-9a-f-]{32,}|(?:app\.)?notion\.com/p/[^\s)]+|simplify\.jobs/profile/[0-9a-f-]{32,})', re.I),
}


def audit(name, body):
    path = Path(name)
    problems = []
    if (name in PRIVATE or path.name.lower() == 'improvements.md'
            or PRIVATE_DIRS.intersection(path.parts)
            or path.suffix.lower() in SUFFIXES or '.sqlite3' in path.name
            or (path.name.startswith('.env') and name != '.env.example')
            or (path.suffix == '.json' and any(word in path.name.lower() for word in ('token', 'credentials', 'client_secret')))):
        problems.append('private file')
    for label, pattern in PATTERNS.items():
        if pattern.search(body):
            problems.append(label)
    for match in EMAIL.finditer(body):
        if (match.group(1).lower() not in MAIL_DOMAINS
                and match.group(0) != 'gmail-api-push@system.gserviceaccount.com'):
            problems.append('non-example email address')
            break
    return problems


def main():
    result = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True)
    if result.returncode:
        raise SystemExit('Run this check from a Git checkout.')
    names = result.stdout.decode().split('\0')
    names = [name for name in names if name]
    if not names:
        raise SystemExit('No tracked files to check; stage the public files first.')
    errors = []
    for name in names:
        path = ROOT / name
        if path.is_symlink() or not path.is_file():
            errors.append(name + ': missing file or symlink')
            continue
        body = path.read_bytes().decode('utf-8', errors='replace')
        errors.extend(name + ': ' + issue for issue in audit(name, body))
        if path.suffix.lower() == '.md':
            for target in re.findall(r'\]\(([^\s)]+)(?:\s+[^)]*)?\)', body):
                url = urlsplit(target.strip('<>'))
                if url.scheme or url.netloc or not url.path:
                    continue
                linked = (path.parent / unquote(url.path)).resolve()
                if not linked.is_relative_to(ROOT) or not linked.exists():
                    errors.append(name + ': broken local link')
    if errors:
        print('\n'.join(sorted(set(errors))))
        raise SystemExit(1)
    print(f'Publication check passed: {len(names)} tracked files. Review your diff before sharing.')


if __name__ == '__main__':
    main()
