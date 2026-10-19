#!/usr/bin/env python3
"""Install/control this project's Gmail monitor as a macOS LaunchAgent."""
import argparse
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import time

from email_monitor import ROOT, RUNTIME

LABEL = 'org.appy.email-monitor'
PLIST = Path.home() / 'Library/LaunchAgents' / (LABEL + '.plist')
DOMAIN = f'gui/{os.getuid()}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['install', 'status', 'stop', 'uninstall'])
    args = parser.parse_args()
    if sys.platform != 'darwin':
        parser.error('This service requires macOS')
    os.umask(0o077)
    if args.command == 'install':
        codex = shutil.which('codex')
        if not codex:
            raise SystemExit('Codex CLI not found')
        python = RUNTIME / 'venv/bin/python'
        config = RUNTIME / 'pubsub.json'
        if not python.exists() or not config.exists():
            raise SystemExit('Complete docs/gmail-monitor.md first; existing service was not changed.')
        # Authenticate and validate read/write tool availability before activation.
        subprocess.run([str(python), str(ROOT / 'email_monitor.py'), '--check', '--codex', codex,
                        '--config', str(config)], check=True)
        RUNTIME.mkdir(parents=True, exist_ok=True)
        PLIST.parent.mkdir(parents=True, exist_ok=True)
        settings = {
            'Label': LABEL,
            'ProgramArguments': [str(python), str(ROOT / 'email_monitor.py'), '--codex', codex,
                                 '--config', str(config)],
            'WorkingDirectory': str(ROOT),
            'EnvironmentVariables': {'PATH': os.environ.get('PATH', '/opt/homebrew/bin:/usr/bin:/bin')},
            'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 30,
            'ProcessType': 'Background',
            'StandardOutPath': str(RUNTIME / 'service.stdout.log'),
            'StandardErrorPath': str(RUNTIME / 'service.stderr.log'),
        }
        loaded = subprocess.run(['launchctl', 'print', DOMAIN + '/' + LABEL], capture_output=True).returncode == 0
        previous = plistlib.loads(PLIST.read_bytes()) if PLIST.exists() else None
        if loaded and previous == settings:
            subprocess.run(['launchctl', 'kickstart', '-k', DOMAIN + '/' + LABEL], check=True)
            print('Restarted: ' + LABEL)
            return
        subprocess.run(['launchctl', 'bootout', DOMAIN + '/' + LABEL], capture_output=True)
        PLIST.write_bytes(plistlib.dumps(settings))
        PLIST.chmod(0o600)
        subprocess.run(['plutil', '-lint', str(PLIST)], check=True)
        # launchd can retain an unloading job briefly after bootout returns.
        for attempt in range(10):
            result = subprocess.run(['launchctl', 'bootstrap', DOMAIN, str(PLIST)], capture_output=True)
            if result.returncode == 0:
                break
            time.sleep(1)
        else:
            raise SystemExit('Unable to load monitor LaunchAgent')
        print('Installed: ' + LABEL)
    elif args.command == 'status':
        result = subprocess.run(['launchctl', 'print', DOMAIN + '/' + LABEL], capture_output=True, text=True)
        if result.returncode:
            print('Monitor is stopped.', flush=True)
        else:
            fields = ('state =', 'pid =', 'last exit code =')
            lines = result.stdout.splitlines()
            print('\n'.join(next((line.strip() for line in lines if field in line), '') for field in fields), flush=True)
            settings = plistlib.loads(PLIST.read_bytes()) if PLIST.exists() else {}
            transport = 'Gmail Pub/Sub StreamingPull' if '--config' in settings.get('ProgramArguments', []) else 'Legacy Gmail polling'
            print('Transport: ' + transport, flush=True)
        if (RUNTIME / 'state.sqlite3').exists():
            subprocess.run([sys.executable, str(ROOT / 'email_monitor.py'), '--status'], check=True)
    else:
        subprocess.run(['launchctl', 'bootout', DOMAIN + '/' + LABEL], capture_output=True)
        if args.command == 'uninstall':
            PLIST.unlink(missing_ok=True)
        print('Monitor stopped.' if args.command == 'stop' else 'Monitor uninstalled.')


if __name__ == '__main__':
    main()
