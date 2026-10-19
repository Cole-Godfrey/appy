#!/usr/bin/env python3
"""Rebuild README artwork from real shortlist.py output with headless Chrome."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'docs/assets'
CHROMES = ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
           '/Applications/Chromium.app/Contents/MacOS/Chromium',
           'google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser']
# view, CSS size, device scale
VIEWS = [('banner', (1280, 600), 2), ('social', (1280, 640), 1), ('terminal', (1280, 940), 2)]


def chrome():
    for candidate in [os.environ.get('CHROME', '')] + CHROMES:
        path = shutil.which(candidate) or (candidate if candidate and Path(candidate).exists() else None)
        if path:
            return path
    raise SystemExit('Chrome or Chromium not found; set CHROME=/path/to/chrome')


def shortlist(*args):
    env = {**os.environ, 'NO_COLOR': '1'}
    return subprocess.check_output([sys.executable, str(ROOT / 'shortlist.py'), *args], text=True, env=env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample', action='store_true', help='Use fictional listings instead of the live feed')
    args = parser.parse_args()
    extra = ['--sample'] if args.sample else []
    data = json.loads(shortlist('--json', *extra))
    data['text'] = shortlist('--limit', '4', *extra).rstrip()
    template = (ROOT / 'scripts/artwork.html').read_text()
    start, end = template.index('/*DATA*/'), template.index('/*END*/')
    page_html = template[:start] + json.dumps(data) + template[end + len('/*END*/'):]
    browser = chrome()
    with tempfile.TemporaryDirectory() as directory:
        page = Path(directory) / 'artwork.html'
        page.write_text(page_html)
        for view, (width, height), scale in VIEWS:
            out = ASSETS / ('social-preview.png' if view == 'social' else view + '.png')
            subprocess.run([browser, '--headless=new', '--hide-scrollbars', '--disable-gpu',
                            f'--user-data-dir={directory}/profile', f'--force-device-scale-factor={scale}',
                            f'--window-size={width},{height}', '--virtual-time-budget=8000',
                            f'--screenshot={out}', f'{page.as_uri()}#{view}'],
                           check=True, capture_output=True, timeout=120)
    print(f"Built banner, social preview and terminal still from {len(data['roles'])} "
          + ('fictional' if args.sample else 'live') + ' listings.')


if __name__ == '__main__':
    main()
