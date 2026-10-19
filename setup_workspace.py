#!/usr/bin/env python3
"""Create private working files; preserve every existing file."""
import argparse
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent


def initialize(root=ROOT):
    root = Path(root)
    (root / 'tmp').mkdir(exist_ok=True)
    (root / 'private').mkdir(exist_ok=True)
    sources = [(root / '.env.example', root / '.env')]
    sources += [(p, root / p.name) for p in sorted((root / 'templates').glob('*.md'))]
    created = []
    for source, target in sources:
        try:
            with target.open('x') as stream:
                stream.write(source.read_text())
            target.chmod(0o600)
            created.append(target.name)
        except FileExistsError:
            continue
    return created


def check(root=ROOT):
    from appy_config import tracker_id
    issues = []
    for name in ('INFORMATION.md', 'QUESTIONS.md', 'NEXT-STEPS.md', 'CAREER-FAIR-COMPANIES.md', '.env'):
        if not (root / name).exists():
            issues.append('Missing ' + name + '; run python3 setup_workspace.py')
    info = root / 'INFORMATION.md'
    if info.exists() and ('[fill in]' in info.read_text() or 'you@example.com' in info.read_text()):
        issues.append('Complete INFORMATION.md')
    try:
        tracker_id()
    except (ValueError, RuntimeError) as error:
        issues.append(str(error))
    if not shutil.which('codex'):
        issues.append('Install Codex CLI for live applications and the optional monitor')
    return issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check local setup without contacting accounts')
    args = parser.parse_args()
    if args.check:
        issues = check()
        print('\n'.join(issues) if issues else 'Local settings ready. Verify connected tools in your agent.')
        raise SystemExit(bool(issues))
    created = initialize()
    print('Created: ' + ', '.join(created) if created else 'Working files already exist; preserved them.')
    print('Next: docs/setup.md')


if __name__ == '__main__':
    main()
