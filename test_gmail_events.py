import json
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest.mock import Mock

from email_monitor import State
from gmail_events import GmailAPI, GmailError, GmailEvents, load_config


class EventTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).parent / 'tmp'
        scratch.mkdir(exist_ok=True)
        self.directory = Path(tempfile.mkdtemp(dir=scratch))
        self.state = State(self.directory / 'state.sqlite3')
        self.state.set(baseline=1000, checkpoint=1000, history_id=10)
        self.gmail, self.catch_up = Mock(), Mock()
        self.gmail.watch.return_value = {'historyId': '50', 'expiration': str(int((time.time() + 604800) * 1000))}
        self.config = {'project_id': 'appy-example-project',
                       'topic': 'projects/appy-example-project/topics/application-email-updates',
                       'subscription': 'projects/appy-example-project/subscriptions/application-email-monitor',
                       'token_file': str(self.directory / 'token.json')}
        self.events = GmailEvents(self.config, self.state, 'test@example.com', self.catch_up,
                                  gmail=self.gmail, subscriber=Mock())

    def tearDown(self):
        self.state.db.close()
        shutil.rmtree(self.directory)

    def notification(self, history_id='30', email='test@example.com'):
        message = Mock()
        message.data = json.dumps({'emailAddress': email, 'historyId': history_id}).encode()
        return message

    def test_history_pagination_only_queues_new_incoming_messages(self):
        self.gmail.history.side_effect = [
            {'historyId': '30', 'history': [{'messagesAdded': [
                {'message': {'id': 'a'}}, {'message': {'id': 'f'}},
                {'message': {'id': 'd', 'labelIds': ['SENT']}}], 'messages': [{'id': 'e'}]}], 'nextPageToken': 'next'},
            {'historyId': '31', 'history': [{'messagesAdded': [{'message': {'id': 'a'}}, {'message': {'id': 'b'}}]}]},
        ]
        self.gmail.metadata.side_effect = lambda mid: {'id': mid, 'internalDate': {'a': '1002000', 'f': '999000', 'b': '1001000'}[mid]}
        message = self.notification()
        message.ack.side_effect = lambda: self.assertEqual(self.state.get('history_id'), '31')
        self.events.notify(message)
        self.assertEqual(self.state.next(), ('b', 0))
        self.assertEqual(self.state.counts(), {'pending': 2})
        message.ack.assert_called_once()
        message.nack.assert_not_called()
        self.assertEqual(self.gmail.history.call_args_list[1].args, ('10', 'next'))

    def test_failed_page_does_not_ack_or_advance_cursor(self):
        self.gmail.history.side_effect = [
            {'historyId': '30', 'history': [{'messagesAdded': [{'message': {'id': 'a'}}]}], 'nextPageToken': 'next'},
            RuntimeError('disconnected'),
        ]
        self.gmail.metadata.return_value = {'id': 'a', 'internalDate': '1002000'}
        message = self.notification()
        self.events.notify(message)
        self.assertEqual(self.state.get('history_id'), '10')
        self.assertEqual(self.state.counts(), {})
        message.ack.assert_not_called()
        message.nack.assert_called_once()

    def test_redelivery_after_restart_does_not_run_or_requeue(self):
        self.state.capture_history([('a', 1002)], '30', 1003)
        self.state.finish('a', 'ignored')
        self.state.db.close()
        self.state = State(self.directory / 'state.sqlite3')
        self.events.state = self.state
        message = self.notification()
        self.events.notify(message)
        self.gmail.history.assert_not_called()
        self.assertEqual(self.state.counts(), {'ignored': 1})
        message.ack.assert_called_once()

    def test_watch_renewal_preserves_unprocessed_history(self):
        self.events.renew()
        self.assertEqual(self.state.get('history_id'), '10')
        self.assertAlmostEqual(float(self.state.get('watch_renew_at')), time.time() + 86400, delta=1)
        self.gmail.history.return_value = {'historyId': '50', 'history': [{'messagesAdded': [{'message': {'id': 'a'}}]}]}
        self.gmail.metadata.return_value = {'id': 'a', 'internalDate': '1002000'}
        self.events.sync()
        self.gmail.history.assert_called_once_with('10', None)
        self.assertEqual(self.state.next(), ('a', 0))

    def test_duplicate_notifications_and_maintenance_do_not_retry_pending_mail(self):
        self.state.capture_history([('a', 1002)], '30', 1003)
        self.assertEqual(self.state.claim_batch(), ['a'])
        self.state.changed.clear()
        self.events.notify(self.notification())
        self.events.renew()
        self.gmail.history.return_value = {'historyId': '50'}
        self.events.sync()
        self.assertFalse(self.state.changed.is_set())
        self.assertIsNone(self.state.next())
        self.assertEqual(self.state.counts(), {'pending': 1})

    def test_recovery_of_new_arrival_releases_failed_queue(self):
        self.state.capture_history([('a', 1002)], '30', 1003)
        self.state.claim_batch()
        self.state.changed.clear()
        self.gmail.history.return_value = {'historyId': '31', 'history': [{'messagesAdded': [{'message': {'id': 'b'}}]}]}
        self.gmail.metadata.return_value = {'id': 'b', 'internalDate': '1004000'}
        self.events.sync()
        self.assertTrue(self.state.changed.is_set())
        self.assertEqual(self.state.claim_batch(), ['a', 'b'])

    def test_expired_cursor_watches_before_catchup(self):
        self.gmail.history.side_effect = GmailError(404)
        order = []
        self.gmail.watch.side_effect = lambda _: order.append('watch') or {'historyId': '50', 'expiration': str(int((time.time() + 604800) * 1000))}
        self.catch_up.side_effect = lambda: order.append('catchup') or self.state.capture([('b', 1002)], 1003)
        self.events.sync()
        self.assertEqual(order, ['watch', 'catchup'])
        self.assertEqual(self.state.get('history_id'), '50')
        self.assertEqual(self.state.next(), ('b', 0))

    def test_failed_recovery_keeps_the_original_cursor(self):
        self.gmail.history.side_effect = GmailError(404)
        self.catch_up.side_effect = RuntimeError('MCP unavailable')
        message = self.notification()
        self.events.notify(message)
        self.assertEqual(self.state.get('history_id'), '10')
        message.nack.assert_called_once()
        message.ack.assert_not_called()

    def test_invalid_or_foreign_notifications_do_not_trigger_an_agent(self):
        for message in [self.notification(email='other@example.com'), self.notification(history_id='bad'), self.notification(history_id=True)]:
            self.events.notify(message)
            message.ack.assert_called_once()
        self.gmail.history.assert_not_called()

    def test_numeric_history_id_from_live_gmail_is_supported(self):
        self.gmail.history.return_value = {'historyId': '30'}
        message = self.notification(history_id=30)
        self.events.notify(message)
        self.assertEqual(self.state.get('history_id'), '30')
        message.ack.assert_called_once()
        message.nack.assert_not_called()

    def test_repeated_page_is_not_committed(self):
        self.gmail.history.return_value = {'historyId': '30', 'nextPageToken': 'same'}
        with self.assertRaises(RuntimeError):
            self.events.sync()
        self.assertEqual(self.state.get('history_id'), '10')

    def test_deleted_mail_is_skipped_but_api_failures_retry(self):
        self.gmail.history.return_value = {'historyId': '30', 'history': [{'messagesAdded': [{'message': {'id': 'a'}}]}]}
        self.gmail.metadata.side_effect = GmailError(403)
        with self.assertRaises(GmailError):
            self.events.sync()
        self.assertEqual(self.state.get('history_id'), '10')
        self.gmail.metadata.side_effect = GmailError(404)
        self.events.sync()
        self.assertEqual(self.state.get('history_id'), '30')
        self.assertEqual(self.state.counts(), {})

    def test_queue_and_cursor_commit_roll_back_together(self):
        with self.state.db:
            self.state.db.execute("CREATE TRIGGER fail_cursor BEFORE UPDATE ON meta WHEN NEW.key='history_id' BEGIN SELECT RAISE(ABORT, 'failed'); END")
            self.state.db.execute("CREATE TRIGGER fail_cursor_insert BEFORE INSERT ON meta WHEN NEW.key='history_id' BEGIN SELECT RAISE(ABORT, 'failed'); END")
        with self.assertRaises(Exception):
            self.state.capture_history([('a', 1002)], '30', 1003)
        self.assertEqual(self.state.get('history_id'), '10')
        self.assertEqual(self.state.counts(), {})
        self.assertEqual(self.state.get('arrival_generation'), '0')
        self.assertFalse(self.state.changed.is_set())

    def test_direct_detector_refuses_mail_writes(self):
        api = GmailAPI.__new__(GmailAPI)
        for method, path in [('POST', 'messages/send'), ('POST', 'messages/a/modify'), ('DELETE', 'messages/a')]:
            with self.assertRaises(ValueError):
                api.request(method, path)

    def test_config_rejects_topic_in_another_project(self):
        self.config['topic'] = 'projects/other-project/topics/application-email-updates'
        path = self.directory / 'config.json'
        path.write_text(json.dumps(self.config))
        with self.assertRaises(ValueError):
            load_config(path)


if __name__ == '__main__':
    unittest.main()
