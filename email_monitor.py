#!/usr/bin/env python3
"""Detect arrivals through Gmail Pub/Sub; run one Codex turn per email."""
import argparse
import fcntl
import json
import logging
from logging.handlers import RotatingFileHandler

from appy_config import tracker_id
import os
from pathlib import Path
import queue
import re
import signal
import sqlite3
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parent
RUNTIME = Path.home() / 'Library/Application Support/Appy'
SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {
        'message_id': {'type': 'string'},
        'outcome': {'type': 'string', 'enum': ['updated', 'ignored', 'needs_review', 'retry']},
    },
    'required': ['message_id', 'outcome'],
}


class RPC:
    """Concurrent JSON-RPC client; never persist protocol/email payloads."""
    def __init__(self, codex, detector=False):
        self.lock = threading.RLock()
        self.pending = {}
        self.listeners = {}
        self.sequence = 0
        self.closed = False
        command = [codex, 'app-server', '-c', 'mcp_servers.playwright.enabled=false',
                   '-c', 'mcp_servers.node_repl.enabled=false']
        if detector:
            command.extend(['-c', 'mcp_servers.notion.enabled=false'])
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, bufsize=1, cwd=ROOT,
        )
        threading.Thread(target=self._read, daemon=True).start()
        try:
            self.call('initialize', {
                'clientInfo': {'name': 'application_email_monitor', 'version': '1.0.0'},
                'capabilities': {'experimentalApi': True},
            })
            self.send({'method': 'initialized', 'params': {}})
        except Exception:
            self.close()
            raise

    def send(self, message):
        with self.lock:
            if self.closed:
                raise RuntimeError('Codex app server disconnected')
            self.process.stdin.write(json.dumps(message) + '\n')
            self.process.stdin.flush()

    def _read(self):
        try:
            for line in self.process.stdout:
                message = json.loads(line)
                with self.lock:
                    if 'id' in message and 'method' not in message:
                        waiter = self.pending.get(message['id'])
                        if waiter is not None:
                            waiter.put(message)
                    elif 'id' in message:
                        # Unexpected interactive requests must fail, never hang the daemon.
                        self.send({'id': message['id'], 'error': {
                            'code': -32601, 'message': 'Unattended monitor: interactive input unavailable',
                        }})
                    else:
                        params = message.get('params', {})
                        listener = self.listeners.get(params.get('threadId'))
                        if listener is not None and message.get('method') in ('item/completed', 'turn/completed'):
                            if message['method'] == 'turn/completed' or params.get('item', {}).get('type') == 'agentMessage':
                                listener.put(message)
        except (OSError, ValueError):
            pass
        finally:
            with self.lock:
                self.closed = True
                error = {'error': {'message': 'Codex app server disconnected'}}
                for waiter in self.pending.values():
                    waiter.put(error)
                for listener in self.listeners.values():
                    listener.put(error)

    def call(self, method, params, timeout=120):
        with self.lock:
            self.sequence += 1
            request_id = self.sequence
            waiter = queue.Queue()
            self.pending[request_id] = waiter
        try:
            self.send({'id': request_id, 'method': method, 'params': params})
            response = waiter.get(timeout=timeout)
            if 'error' in response:
                # Upstream errors can include email data: do not include them in logs.
                raise RuntimeError('Codex RPC failed: ' + method)
            return response['result']
        finally:
            with self.lock:
                self.pending.pop(request_id, None)

    def thread(self, sandbox='read-only'):
        return self.call('thread/start', {
            'cwd': str(ROOT), 'ephemeral': True,
            'approvalPolicy': 'never', 'sandbox': sandbox,
        })['thread']['id']

    def tool(self, thread_id, name, arguments):
        if name not in ('gmail.get_profile', 'gmail.search_emails', 'gmail.read_email'):
            raise ValueError('Detector permits only read calls')
        if name == 'gmail.read_email' and arguments.get('format') != 'minimal':
            raise ValueError('Detector reads delivery metadata only')
        result = self.call('mcpServer/tool/call', {
            'threadId': thread_id, 'server': 'codex_apps',
            'tool': name, 'arguments': arguments,
        })
        if result.get('isError'):
            raise RuntimeError('Gmail MCP call failed')
        data = result.get('structuredContent')
        if data is None:
            texts = [c['text'] for c in result.get('content', []) if c.get('type') == 'text']
            data = json.loads(texts[0])
        if not isinstance(data, dict):
            raise RuntimeError('Unexpected Gmail MCP response')
        return data

    def process_email(self, message_id):
        if not re.fullmatch(r'[0-9a-f]+', message_id):
            raise ValueError('Invalid Gmail message ID')
        thread_id = self.thread('workspace-write')
        events = queue.Queue()
        with self.lock:
            self.listeners[thread_id] = events
        try:
            prompt = (
                'Process Gmail message ID ' + message_id + '. '
                'Read and follow EMAIL_MONITOR.md and APPLICATION_GUIDE.md in this project. '
                'This is one incoming-email event, not an application batch or backlog scan. '
                'Use Gmail and Notion MCP. Change only the matching tracker row, NEXT-STEPS.md, '
                'or QUESTIONS.md as the workflow requires. Do not modify Gmail or send messages. '
                'Report retry if any required update or verification fails. '
                'Return only the requested JSON with this exact message_id and outcome.'
            )
            turn = self.call('turn/start', {
                'threadId': thread_id, 'input': [{'type': 'text', 'text': prompt}],
                'outputSchema': SCHEMA,
            })['turn']['id']
            deadline = time.monotonic() + 1200
            final = None
            while time.monotonic() < deadline:
                event = events.get(timeout=max(0.01, deadline - time.monotonic()))
                if 'error' in event:
                    raise RuntimeError('Email turn disconnected')
                params = event['params']
                if params.get('turnId', params.get('turn', {}).get('id')) != turn:
                    continue
                if event['method'] == 'item/completed':
                    final = params['item'].get('text')
                elif event['method'] == 'turn/completed':
                    if params['turn']['status'] != 'completed' or not final:
                        raise RuntimeError('Email turn failed')
                    result = json.loads(final)
                    if result.get('message_id') != message_id or result.get('outcome') not in SCHEMA['properties']['outcome']['enum']:
                        raise RuntimeError('Invalid email turn result')
                    return result['outcome']
            raise TimeoutError('Email turn timed out')
        except (queue.Empty, TimeoutError):
            try:
                self.call('turn/interrupt', {'threadId': thread_id, 'turnId': turn}, timeout=10)
            except Exception:
                pass
            raise TimeoutError('Email turn timed out') from None
        finally:
            with self.lock:
                self.listeners.pop(thread_id, None)
            try:
                self.call('thread/unsubscribe', {'threadId': thread_id}, timeout=10)
            except Exception:
                pass

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.process.stdin.close()
        self.process.stdout.close()


class State:
    """Only technical cursors/IDs/retry state; application records remain in Notion."""
    def __init__(self, path):
        self.lock = threading.RLock()
        self.changed = threading.Event()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY, received REAL NOT NULL,
                outcome TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                attempted_generation INTEGER NOT NULL DEFAULT 0
            );
        ''')
        with self.db:
            columns = {row[1] for row in self.db.execute('PRAGMA table_info(messages)')}
            if 'attempted_generation' not in columns:
                self.db.execute('ALTER TABLE messages ADD COLUMN attempted_generation INTEGER NOT NULL DEFAULT 0')
            self.db.execute("INSERT OR IGNORE INTO meta VALUES ('checkpoint', ?)", (str(time.time()),))
            self.db.execute("INSERT OR IGNORE INTO meta VALUES ('arrival_generation', '0')")
        if self.next() is not None:
            self.changed.set()

    def checkpoint(self):
        with self.lock:
            return float(self.db.execute("SELECT value FROM meta WHERE key='checkpoint'").fetchone()[0])

    def baseline(self):
        with self.lock:
            return float(self.db.execute("SELECT value FROM meta WHERE key='baseline'").fetchone()[0])

    def capture(self, messages, checkpoint):
        # Advance only after the entire paginated search has succeeded.
        with self.lock, self.db:
            added = self._capture_messages(messages)
            self.db.execute("UPDATE meta SET value=? WHERE key='checkpoint'", (str(checkpoint),))
        if added:
            self.changed.set()

    def _capture_messages(self, messages):
        previous = self.db.total_changes
        self.db.executemany('INSERT OR IGNORE INTO messages (id, received) VALUES (?, ?)', messages)
        added = self.db.total_changes - previous
        if added:
            self.db.execute("UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='arrival_generation'")
        return added

    def next(self):
        with self.lock:
            return self.db.execute(
                "SELECT id, attempts FROM messages WHERE outcome='pending' AND attempted_generation < ? ORDER BY received, id LIMIT 1",
                (int(self.get('arrival_generation')),),
            ).fetchone()

    def claim_batch(self):
        # Each pending email gets at most one attempt per newly captured arrival batch.
        # Save the claim before MCP access so a restart cannot retry a failed grant.
        with self.lock, self.db:
            generation = int(self.get('arrival_generation'))
            messages = [row[0] for row in self.db.execute(
                "SELECT id FROM messages WHERE outcome='pending' AND attempted_generation < ? ORDER BY received, id",
                (generation,),
            )]
            self.db.execute(
                "UPDATE messages SET attempted_generation=?, attempts=attempts+1 WHERE outcome='pending' AND attempted_generation < ?",
                (generation, generation),
            )
            return messages

    def seen(self, message_id):
        with self.lock:
            return self.db.execute('SELECT 1 FROM messages WHERE id=?', (message_id,)).fetchone() is not None

    def finish(self, message_id, outcome):
        if outcome not in ('updated', 'ignored', 'needs_review'):
            raise ValueError('Cannot acknowledge an incomplete update')
        with self.lock, self.db:
            self.db.execute('UPDATE messages SET outcome=? WHERE id=?', (outcome, message_id))

    def counts(self):
        with self.lock:
            return dict(self.db.execute('SELECT outcome, COUNT(*) FROM messages GROUP BY outcome'))

    def get(self, key, default=None):
        with self.lock:
            row = self.db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
            return row[0] if row else default

    def set(self, **values):
        with self.lock, self.db:
            self.db.executemany('INSERT OR REPLACE INTO meta VALUES (?, ?)',
                                [(key, str(value)) for key, value in values.items()])

    def capture_history(self, messages, history_id, checkpoint):
        # Persist every arrival and its history cursor in one transaction before ack.
        with self.lock, self.db:
            previous = self.get('history_id')
            if previous is not None and int(history_id) < int(previous):
                raise ValueError('Gmail history cursor cannot move backwards')
            added = self._capture_messages(messages)
            self.db.executemany('INSERT OR REPLACE INTO meta VALUES (?, ?)', [
                ('history_id', str(history_id)), ('checkpoint', str(max(checkpoint, self.checkpoint()))),
                ('last_history_sync', str(time.time())),
            ])
        if added:
            self.changed.set()


def account_email():
    match = re.search(r'^- Email:\s*(\S+)', (ROOT / 'INFORMATION.md').read_text(), re.M)
    if not match:
        raise RuntimeError('Applicant email missing')
    return match.group(1).lower()


def capture(rpc, thread_id, state):
    since = state.checkpoint()
    baseline = state.baseline()
    started = time.time()
    query_text = f'in:anywhere -in:trash -in:sent -in:drafts after:{int(since) - 300}'
    found = {}
    token = None
    visited = set()
    while True:
        args = {'query': query_text, 'max_results': 100}
        if token:
            args['next_page_token'] = token
        result = rpc.tool(thread_id, 'gmail.search_emails', args)
        if not isinstance(result.get('emails'), list):
            raise RuntimeError('Incomplete Gmail search')
        for email in result['emails']:
            if {'SENT', 'DRAFT', 'TRASH'} & set(email.get('labels', [])):
                continue
            message_id = email['id']
            if not re.fullmatch(r'[0-9a-f]+', message_id):
                raise RuntimeError('Invalid Gmail search ID')
            if state.seen(message_id) or message_id in found:
                continue
            metadata = rpc.tool(thread_id, 'gmail.read_email', {'message_id': message_id, 'format': 'minimal'})
            if metadata.get('id') != message_id or 'internal_date' not in metadata:
                raise RuntimeError('Incomplete Gmail delivery metadata')
            if {'SENT', 'DRAFT', 'TRASH'} & set(metadata.get('label_ids', [])):
                continue
            # Search and queue use server delivery time, never the sender's Date header.
            received = int(metadata['internal_date']) / 1000
            # The initial cursor excludes the backlog; later scans retain overlap.
            if received >= baseline:
                found[message_id] = received
        token = result.get('next_page_token')
        if not token:
            break
        if token in visited:
            raise RuntimeError('Repeated Gmail pagination token')
        visited.add(token)
    state.capture(sorted(found.items(), key=lambda item: (item[1], item[0])), max(since, started))


def verify_notion(rpc):
    thread = rpc.thread()
    inventory = rpc.call('mcpServerStatus/list', {'threadId': thread, 'detail': 'toolsAndAuthOnly'})
    notion = next((s for s in inventory['data'] if s['name'] == 'notion'), None)
    if not notion or 'notion-update-page' not in notion.get('tools', {}):
        raise RuntimeError('Notion MCP unavailable')
    verified = rpc.call('mcpServer/tool/call', {
        'threadId': thread, 'server': 'notion', 'tool': 'notion-fetch',
        'arguments': {'id': tracker_id()},
    })
    if verified.get('isError'):
        raise RuntimeError('Notion tracker unavailable')


class EmailWorker:
    def __init__(self, rpc_factory, state, stop):
        self.rpc_factory, self.state, self.stop = rpc_factory, state, stop
        self.lock = threading.RLock()
        self.rpc = None

    def process_pending(self):
        messages = self.state.claim_batch()
        if not messages or self.stop.is_set():
            return
        rpc = None
        try:
            # Reload stored OAuth credentials on each arrival, including a manual login.
            rpc = self.rpc_factory()
            with self.lock:
                if self.stop.is_set():
                    rpc.close()
                    return
                self.rpc = rpc
            verify_notion(rpc)
            for message_id in messages:
                if self.stop.is_set():
                    break
                try:
                    outcome = rpc.process_email(message_id)
                    if outcome == 'retry':
                        raise RuntimeError('Agent requested retry')
                    self.state.finish(message_id, outcome)
                    logging.info('Email %s: %s', message_id, outcome)
                except Exception as error:
                    logging.warning('Email %s: pending until a new arrival (%s)', message_id, type(error).__name__)
                    if rpc.closed:
                        break
        except Exception as error:
            logging.warning('MCP unavailable; pending queue waits for a new arrival (%s)', type(error).__name__)
        finally:
            with self.lock:
                if self.rpc is rpc and rpc is not None:
                    self.rpc = None
                    rpc.close()

    def run(self):
        while not self.stop.is_set():
            self.state.changed.wait()
            self.state.changed.clear()
            if not self.stop.is_set():
                self.process_pending()

    def close(self):
        self.stop.set()
        self.state.changed.set()
        with self.lock:
            if self.rpc is not None:
                self.rpc.close()
                self.rpc = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex', default='codex')
    parser.add_argument('--config', type=Path, default=RUNTIME / 'pubsub.json', help='Gmail Pub/Sub configuration')
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--check', action='store_true', help='Check Gmail and Notion access without running an agent')
    parser.add_argument('--since', type=float, help='Initial arrival cutoff (epoch seconds); existing state is preserved')
    args = parser.parse_args()
    os.umask(0o077)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    state = State(RUNTIME / 'state.sqlite3')
    with state.db:
        state.db.execute("INSERT OR IGNORE INTO meta VALUES ('baseline', ?)", (str(args.since if args.since is not None else state.checkpoint()),))
        if args.since is not None and not state.db.execute('SELECT 1 FROM messages LIMIT 1').fetchone():
            baseline = float(state.db.execute("SELECT value FROM meta WHERE key='baseline'").fetchone()[0])
            state.db.execute("UPDATE meta SET value=? WHERE key='checkpoint'", (str(baseline),))
    if args.status:
        print(json.dumps({'checkpoint': state.checkpoint(), 'history_id': state.get('history_id'),
                          'watch_expires': state.get('watch_expires'), 'counts': state.counts()}))
        return
    lock = open(RUNTIME / 'monitor.lock', 'a')
    if not args.check:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Monitor already running')
    handler = RotatingFileHandler(RUNTIME / 'monitor.log', maxBytes=1_000_000, backupCount=2)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', handlers=[handler])
    rpc = RPC(args.codex, detector=True)
    stop = threading.Event()
    worker = EmailWorker(lambda: RPC(args.codex), state, stop)
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    try:
        detector_thread = rpc.thread()
        profile = rpc.tool(detector_thread, 'gmail.get_profile', {})
        if profile.get('email', '').lower() != account_email():
            raise RuntimeError('Connected Gmail account does not match INFORMATION.md')
        from gmail_events import GmailEvents, load_config
        events = GmailEvents(load_config(args.config), state, account_email(),
                             lambda: capture(rpc, detector_thread, state))
        events.check()
        if args.check:
            events.subscriber.close()
            events.gmail.session.close()
            notion_rpc = RPC(args.codex)
            try:
                verify_notion(notion_rpc)
            finally:
                notion_rpc.close()
            print('Gmail account and Notion tracker verified; Pub/Sub verified.')
            return
        threading.Thread(target=worker.run, daemon=True).start()
        logging.info('Monitor started; Gmail Pub/Sub StreamingPull')
        events.run(stop, lambda: rpc.closed)
    except Exception as error:
        logging.error('Monitor restarting: %s', type(error).__name__)
        raise SystemExit(1) from None
    finally:
        worker.close()
        rpc.close()
        lock.close()


if __name__ == '__main__':
    main()
