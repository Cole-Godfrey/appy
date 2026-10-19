#!/usr/bin/env python3
"""Authorize the Mac Gmail monitor with a project-owned desktop OAuth client."""
import argparse
import json
import os
from pathlib import Path

from email_monitor import RUNTIME, account_email
from gmail_events import GMAIL_SCOPE


def private_json(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w') as file:
        json.dump(value, file)
        file.flush()
        os.fsync(file.fileno())
    Path(path).chmod(0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client', type=Path, required=True, help='Downloaded Desktop app OAuth client JSON')
    parser.add_argument('--project', required=True)
    parser.add_argument('--topic', default='application-email-updates')
    parser.add_argument('--subscription', default='application-email-monitor')
    parser.add_argument('--no-browser', action='store_true', help='Print the consent URL instead of opening it')
    args = parser.parse_args()
    os.umask(0o077)
    from google.auth.transport.requests import AuthorizedSession
    from google_auth_oauthlib.flow import InstalledAppFlow
    client = json.loads(args.client.read_text())
    if client.get('installed', {}).get('project_id') != args.project:
        parser.error('Use a Desktop app OAuth client from the selected Pub/Sub project')
    flow = InstalledAppFlow.from_client_config(client, [GMAIL_SCOPE])
    credentials = flow.run_local_server(host='127.0.0.1', port=0, open_browser=not args.no_browser,
                                        timeout_seconds=600, prompt='consent', login_hint=account_email(),
                                        success_message='Gmail monitor authorized. You may close this tab.')
    if not credentials.refresh_token:
        raise SystemExit('No offline token granted; run authorization again')
    with AuthorizedSession(credentials) as session:
        response = session.get('https://gmail.googleapis.com/gmail/v1/users/me/profile', timeout=60)
        if not response.ok:
            raise SystemExit('Gmail profile verification failed: HTTP ' + str(response.status_code))
        if response.json().get('emailAddress', '').lower() != account_email():
            raise SystemExit('Authorize the Gmail account in INFORMATION.md')
    RUNTIME.mkdir(parents=True, exist_ok=True)
    token_file = RUNTIME / 'gmail-token.json'
    private_json(token_file, json.loads(credentials.to_json()))
    private_json(RUNTIME / 'pubsub.json', {
        'project_id': args.project,
        'topic': f'projects/{args.project}/topics/{args.topic}',
        'subscription': f'projects/{args.project}/subscriptions/{args.subscription}',
        'token_file': str(token_file),
    })
    print('Gmail authorized. Activate with: python3 monitor_service.py install')


if __name__ == '__main__':
    main()
