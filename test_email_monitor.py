from pathlib import Path
import shutil
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from email_monitor import EmailWorker, RPC, State, capture, main, verify_notion


class MonitorTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).parent / 'tmp'
        scratch.mkdir(exist_ok=True)
        self.directory = Path(tempfile.mkdtemp(dir=scratch))
        self.state = State(self.directory / 'state.sqlite3')
        with self.state.db:
            self.state.db.execute("INSERT INTO meta VALUES ('baseline', '1000')")
            self.state.db.execute("UPDATE meta SET value='1000' WHERE key='checkpoint'")

    def tearDown(self):
        self.state.db.close()
        shutil.rmtree(self.directory)

    def email(self, message_id, timestamp, labels=None):
        from datetime import datetime, timezone
        return {'id': message_id, 'email_ts': datetime.fromtimestamp(timestamp, timezone.utc).isoformat(), 'labels': labels or []}

    def test_pagination_dedup_and_backlog_exclusion(self):
        pages = [
            {'emails': [self.email('a', 1002), self.email('f', 999)], 'next_page_token': 'next'},
            {'emails': [self.email('b', 1001), self.email('a', 1002), self.email('c', 1003, ['SENT'])]},
        ]
        class Gmail:
            def tool(_, thread, name, arguments):
                if name == 'gmail.read_email':
                    mid = arguments['message_id']
                    return {'id': mid, 'internal_date': {'a': '1002000', 'b': '1001000', 'f': '999000'}[mid]}
                return pages.pop(0)
        capture(Gmail(), 'thread', self.state)
        self.assertEqual(self.state.next(), ('b', 0))
        self.assertEqual(self.state.counts(), {'pending': 2})
        self.state.finish('b', 'updated')
        self.state.capture([('b', 1001)], self.state.checkpoint())
        self.assertEqual(self.state.next(), ('a', 0))

    def test_failure_does_not_advance_cursor_or_save_partial_page(self):
        class Gmail:
            def tool(_, thread, name, arguments):
                if name == 'gmail.read_email':
                    return {'id': 'a', 'internal_date': '1002000'}
                if arguments.get('next_page_token'):
                    raise RuntimeError('Disconnected')
                return {'emails': [self.email('a', 1002)], 'next_page_token': 'next'}
        with self.assertRaises(RuntimeError):
            capture(Gmail(), 'thread', self.state)
        self.assertEqual(self.state.checkpoint(), 1000)
        self.assertEqual(self.state.counts(), {})

    def test_repeated_pagination_token_is_failure(self):
        class Gmail:
            def tool(_, *args):
                return {'emails': [], 'next_page_token': 'same'}
        with self.assertRaises(RuntimeError):
            capture(Gmail(), 'thread', self.state)
        self.assertEqual(self.state.checkpoint(), 1000)

    def test_retry_survives_restart_and_does_not_acknowledge(self):
        self.state.capture([('a', 1001)], 1002)
        with self.assertRaises(ValueError):
            self.state.finish('a', 'retry')
        self.assertEqual(self.state.claim_batch(), ['a'])
        self.assertIsNone(self.state.next())
        self.state.db.close()
        self.state = State(self.directory / 'state.sqlite3')
        self.assertEqual(self.state.counts(), {'pending': 1})
        with patch('email_monitor.time.time', return_value=time.time() + 86400):
            self.assertIsNone(self.state.next())
        self.state.capture([('b', 1003)], 1004)
        self.assertEqual(self.state.next(), ('a', 1))

    def worker(self, rpc=None):
        rpc = rpc or Mock(closed=False)
        rpc.process_email.return_value = 'updated'
        factory = Mock(return_value=rpc)
        return EmailWorker(factory, self.state, threading.Event()), rpc, factory

    @patch('email_monitor.verify_notion')
    def test_notion_outage_queues_all_mail_without_idle_retries(self, verify):
        verify.side_effect = RuntimeError('Notion unavailable')
        worker, rpc, factory = self.worker()
        self.state.capture([('a', 1001), ('b', 1002)], 1003)
        worker.process_pending()
        self.assertEqual(self.state.counts(), {'pending': 2})
        rpc.process_email.assert_not_called()
        rpc.close.assert_called_once()
        for messages in [[], [('a', 1001)], [('b', 1002)]]:
            self.state.capture(messages, 1004)
            worker.process_pending()
        factory.assert_called_once()
        verify.assert_called_once()
        self.assertFalse(worker.stop.is_set())

    @patch('email_monitor.verify_notion')
    def test_new_mail_reloads_credentials_and_drains_failed_queue(self, verify):
        verify.side_effect = [RuntimeError('Notion unavailable'), None]
        worker, rpc, factory = self.worker()
        restored_rpc = Mock(closed=False)
        restored_rpc.process_email.return_value = 'updated'
        factory.side_effect = [rpc, restored_rpc]
        self.state.capture([('a', 1001)], 1002)
        worker.process_pending()
        self.state.capture([('b', 1003)], 1004)
        worker.process_pending()
        self.assertEqual(self.state.counts(), {'updated': 2})
        self.assertEqual([call.args[0] for call in restored_rpc.process_email.call_args_list], ['a', 'b'])
        self.assertEqual(verify.call_count, 2)
        self.assertEqual(factory.call_count, 2)
        restored_rpc.close.assert_called_once()

    @patch('email_monitor.verify_notion')
    def test_failed_turn_stays_pending_without_blocking_other_messages(self, verify):
        worker, rpc, factory = self.worker()
        rpc.process_email.side_effect = ['retry', 'ignored']
        self.state.capture([('a', 1001), ('b', 1002)], 1003)
        worker.process_pending()
        self.assertEqual(self.state.counts(), {'pending': 1, 'ignored': 1})
        worker.process_pending()
        factory.assert_called_once()
        rpc.process_email.side_effect = None
        self.state.capture([('c', 1004)], 1005)
        worker.process_pending()
        self.assertEqual([call.args[0] for call in rpc.process_email.call_args_list], ['a', 'b', 'a', 'c'])
        self.assertEqual(self.state.counts(), {'updated': 2, 'ignored': 1})

    @patch('email_monitor.verify_notion')
    def test_arrival_during_processing_remains_a_retry_trigger(self, verify):
        worker, rpc, _ = self.worker()
        self.state.capture([('a', 1001)], 1002)
        self.state.changed.clear()
        def process(message_id):
            if message_id == 'a':
                self.state.capture([('b', 1003)], 1004)
                return 'retry'
            return 'ignored'
        rpc.process_email.side_effect = process
        worker.process_pending()
        self.assertTrue(self.state.changed.is_set())
        self.assertEqual(self.state.next(), ('a', 1))
        rpc.process_email.side_effect = None
        worker.process_pending()
        self.assertEqual(self.state.counts(), {'updated': 2})

    @patch('email_monitor.verify_notion')
    def test_disconnected_processing_keeps_capture_and_queue_alive(self, verify):
        worker, rpc, _ = self.worker()
        rpc.closed = True
        rpc.process_email.side_effect = RuntimeError('Disconnected')
        self.state.capture([('a', 1001), ('b', 1002)], 1003)
        worker.process_pending()
        self.assertEqual(self.state.counts(), {'pending': 2})
        self.assertFalse(worker.stop.is_set())
        self.assertIsNone(self.state.next())
        self.state.capture([('c', 1004)], 1005)
        self.assertEqual(self.state.counts(), {'pending': 3})

    def test_legacy_timed_retry_migrates_without_retrying_on_startup(self):
        path = self.directory / 'legacy.sqlite3'
        db = sqlite3.connect(path)
        try:
            with db:
                db.execute("CREATE TABLE messages (id TEXT PRIMARY KEY, received REAL NOT NULL, outcome TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0, retry_at REAL NOT NULL DEFAULT 0)")
                db.execute("INSERT INTO messages VALUES ('a', 1001, 'pending', 3, 0)")
        finally:
            db.close()
        state = State(path)
        try:
            self.assertIsNone(state.next())
            self.assertFalse(state.changed.is_set())
            self.assertEqual(state.claim_batch(), [])
            state.capture([('b', 1003)], 1004)
            self.assertEqual(state.claim_batch(), ['a', 'b'])
            self.assertEqual(state.counts(), {'pending': 2})
        finally:
            state.db.close()

    def test_unclaimed_arrival_survives_restart(self):
        self.state.capture([('a', 1001)], 1002)
        self.state.db.close()
        self.state = State(self.directory / 'state.sqlite3')
        self.assertTrue(self.state.changed.is_set())
        self.assertEqual(self.state.claim_batch(), ['a'])

    def test_worker_shutdown_wakes_without_polling(self):
        worker, _, factory = self.worker()
        thread = threading.Thread(target=worker.run)
        thread.start()
        worker.close()
        thread.join(timeout=1)
        self.assertFalse(thread.is_alive())
        factory.assert_not_called()

    @patch('email_monitor.tracker_id', return_value='collection://11111111-1111-4111-8111-111111111111')
    def test_notion_check_rejects_missing_tools_and_failed_fetch(self, tracker):
        rpc = Mock()
        rpc.call.return_value = {'data': []}
        with self.assertRaises(RuntimeError):
            verify_notion(rpc)
        rpc.call.side_effect = [
            {'data': [{'name': 'notion', 'tools': {'notion-update-page': {}}}]},
            {'isError': True},
        ]
        with self.assertRaises(RuntimeError):
            verify_notion(rpc)

    def test_monitor_startup_captures_mail_without_notion_access(self):
        rpc = Mock(closed=False)
        rpc.tool.return_value = {'email': 'test@example.com'}
        with patch('email_monitor.RUNTIME', self.directory), \
             patch('email_monitor.State', return_value=self.state), \
             patch('email_monitor.RPC', return_value=rpc) as factory, \
             patch('email_monitor.account_email', return_value='test@example.com'), \
             patch('email_monitor.verify_notion', side_effect=RuntimeError('Notion unavailable')) as verify, \
             patch('email_monitor.RotatingFileHandler'), \
             patch('email_monitor.logging.basicConfig'), \
             patch('email_monitor.signal.signal'), \
             patch('email_monitor.threading.Thread') as thread, \
             patch('gmail_events.load_config', return_value={}), \
             patch('gmail_events.GmailEvents') as events, \
             patch('sys.argv', ['email_monitor.py']):
            events.return_value.run.side_effect = lambda *_: self.state.capture_history([('a', 1001)], '30', 1002)
            main()
        verify.assert_not_called()
        factory.assert_called_once_with('codex', detector=True)
        events.return_value.check.assert_called_once()
        events.return_value.run.assert_called_once()
        thread.return_value.start.assert_called_once()
        self.assertEqual(self.state.counts(), {'pending': 1})
        rpc.close.assert_called_once()

    def test_detector_refuses_mail_mutations(self):
        rpc = RPC.__new__(RPC)
        with self.assertRaises(ValueError):
            rpc.tool('thread', 'gmail.send_email', {})

    def test_delayed_delivery_uses_server_time_instead_of_sender_date(self):
        class Gmail:
            def tool(_, thread, name, arguments):
                if name == 'gmail.read_email':
                    return {'id': 'a', 'internal_date': '1002000'}
                return {'emails': [self.email('a', 500)]}
        capture(Gmail(), 'thread', self.state)
        self.assertEqual(self.state.next(), ('a', 0))


if __name__ == '__main__':
    unittest.main()
