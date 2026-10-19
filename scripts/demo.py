#!/usr/bin/env python3
"""Run real discovery filters on fictional fixtures, offline."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from discover_jobs import exclude_duplicates, simplify_jobs  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    rows = json.loads((ROOT / 'examples/listings.json').read_text())
    tracker = json.loads((ROOT / 'examples/tracker.json').read_text())
    candidates = simplify_jobs(rows, 2027)
    jobs = exclude_duplicates(candidates, tracker, 2027)
    if args.json:
        print(json.dumps({'jobs': jobs, 'warnings': [], 'demo': True}, indent=2))
        return
    print('Appy / offline demo\n')
    print(f'{len(candidates)} fictional listings read')
    print(f'{len(candidates) - len(jobs)} already tracked; skipped')
    print(f'{len(jobs)} roles in your shortlist\n')
    for job in jobs:
        print(job['company'])
        print('  ' + job['title'])
        print('  ' + job['url'] + '\n')
    print('No accounts connected. No applications submitted.')


if __name__ == '__main__':
    main()
