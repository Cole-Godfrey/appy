"""Gmail watch/history API and a persistent Cloud Pub/Sub subscriber."""
import json
import logging
from pathlib import Path
import re
import threading
import time

GMAIL_SCOPE = 'https://www.googleapis.com/auth/gmail.metadata'
CLOUD_SCOPE = 'https://www.googleapis.com/auth/cloud-platform'
IGNORED_LABELS = {'SENT', 'DRAFT', 'TRASH'}


def load_config(path):
    config = json.loads(Path(path).read_text())
    project = config['project_id']
    if not re.fullmatch(r'[a-z][a-z0-9-]{4,28}[a-z0-9]', project):
        raise ValueError('Invalid Cloud project')
    for key, resource in [('topic', 'topics'), ('subscription', 'subscriptions')]:
        if not re.fullmatch(r'projects/' + re.escape(project) + '/' + resource + r'/[A-Za-z][A-Za-z0-9._~-]{2,254}', config[key]):
            raise ValueError('Pub/Sub resources must belong to the configured project')
    if not Path(config['token_file']).is_absolute():
        raise ValueError('OAuth token path must be absolute')
    return config


class GmailError(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__('Gmail API HTTP ' + str(status))


class GmailAPI:
    def __init__(self, token_file):
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2.credentials import Credentials
        credentials = Credentials.from_authorized_user_file(token_file, [GMAIL_SCOPE])
        if not credentials.refresh_token or not credentials.has_scopes([GMAIL_SCOPE]):
            raise RuntimeError('Authorize Gmail metadata access first')
        self.session = AuthorizedSession(credentials)

    def request(self, method, endpoint, **kwargs):
        allowed = (method, endpoint) in {('GET', 'profile'), ('GET', 'history'), ('POST', 'watch')}
        if not allowed and not (method == 'GET' and re.fullmatch(r'messages/[0-9a-f]+', endpoint)):
            raise ValueError('Detector permits only metadata reads and watch registration')
        response = self.session.request(method, 'https://gmail.googleapis.com/gmail/v1/users/me/' + endpoint,
                                        timeout=60, **kwargs)
        if not response.ok:
            # Never log response payloads, authorization headers, or token values.
            raise GmailError(response.status_code)
        return response.json()

    def profile(self):
        return self.request('GET', 'profile')

    def watch(self, topic):
        # Watch the whole mailbox, including Spam and automatic filtering.
        return self.request('POST', 'watch', json={'topicName': topic})

    def history(self, history_id, token=None):
        params = {'startHistoryId': history_id, 'historyTypes': 'messageAdded', 'maxResults': 500}
        if token:
            params['pageToken'] = token
        return self.request('GET', 'history', params=params)

    def metadata(self, message_id):
        return self.request('GET', 'messages/' + message_id,
                            params={'format': 'minimal', 'fields': 'id,labelIds,internalDate'})


class GmailEvents:
    def __init__(self, config, state, email, catch_up, gmail=None, subscriber=None):
        self.config, self.state, self.email, self.catch_up = config, state, email, catch_up
        self.gmail = gmail or GmailAPI(config['token_file'])
        self.subscriber = subscriber
        self.lock = threading.RLock()

    def check(self):
        if self.gmail.profile().get('emailAddress', '').lower() != self.email:
            raise RuntimeError('Gmail OAuth account does not match INFORMATION.md')
        if self.subscriber is None:
            import google.auth
            from google.cloud import pubsub_v1
            credentials, _ = google.auth.default(scopes=[CLOUD_SCOPE], quota_project_id=self.config['project_id'])
            self.subscriber = pubsub_v1.SubscriberClient(credentials=credentials)
        subscription = self.subscriber.get_subscription(request={'subscription': self.config['subscription']})
        if subscription.topic != self.config['topic'] or subscription.push_config.push_endpoint:
            raise RuntimeError('Expected a pull subscription for the configured Gmail topic')

    def renew(self):
        result = self.gmail.watch(self.config['topic'])
        history_id = str(result.get('historyId', ''))
        expires = int(result['expiration']) / 1000
        now = time.time()
        if not re.fullmatch(r'[0-9]+', history_id) or expires <= now + 3600:
            raise RuntimeError('Invalid Gmail watch response')
        # Renewing a watch must never replace the durable history cursor.
        self.state.set(watch_expires=expires, watch_renew_at=min(now + 86400, expires - 3600),
                       pubsub_topic=self.config['topic'])
        logging.info('Gmail watch renewed')
        return history_id

    def recover(self):
        # Establish the watch first, then bridge missed mail with the existing MCP.
        # New arrivals after this watch remain recoverable through history.list.
        history_id = self.renew()
        self.catch_up()
        self.state.capture_history([], history_id, self.state.checkpoint())
        logging.info('Gmail history initialized/recovered')

    def sync(self):
        with self.lock:
            cursor = self.state.get('history_id')
            if cursor is None:
                self.recover()
                return
            started = time.time()
            found, visited, token = {}, set(), None
            try:
                while True:
                    result = self.gmail.history(cursor, token)
                    history_id = str(result.get('historyId', ''))
                    if not re.fullmatch(r'[0-9]+', history_id) or int(history_id) < int(cursor):
                        raise RuntimeError('Invalid Gmail history response')
                    for record in result.get('history', []):
                        for change in record.get('messagesAdded', []):
                            message = change['message']
                            message_id = message['id']
                            if not re.fullmatch(r'[0-9a-f]+', message_id):
                                raise RuntimeError('Invalid Gmail message ID')
                            if message_id in found or self.state.seen(message_id) or IGNORED_LABELS & set(message.get('labelIds', [])):
                                continue
                            try:
                                metadata = self.gmail.metadata(message_id)
                            except GmailError as error:
                                if error.status == 404:  # Deleted before delivery to this subscriber.
                                    continue
                                raise
                            if metadata.get('id') != message_id or 'internalDate' not in metadata:
                                raise RuntimeError('Incomplete Gmail delivery metadata')
                            if not IGNORED_LABELS & set(metadata.get('labelIds', [])):
                                received = int(metadata['internalDate']) / 1000
                                if received >= self.state.baseline():
                                    found[message_id] = received
                    token = result.get('nextPageToken')
                    if not token:
                        break
                    if token in visited:
                        raise RuntimeError('Repeated Gmail history page')
                    visited.add(token)
            except GmailError as error:
                if error.status != 404:
                    raise
                self.recover()
                return
            self.state.capture_history(sorted(found.items(), key=lambda item: (item[1], item[0])), history_id, started)

    def notify(self, message):
        try:
            event = json.loads(message.data)
            history_id = event.get('historyId')
            if isinstance(history_id, bool) or not isinstance(history_id, (str, int)):
                raise ValueError('Unexpected Gmail history ID')
            history_id = str(history_id)
            if event.get('emailAddress', '').lower() != self.email or not re.fullmatch(r'[0-9]+', history_id):
                raise ValueError('Unexpected Gmail notification')
        except (ValueError, TypeError, AttributeError):
            logging.warning('Discarded invalid Pub/Sub notification')
            message.ack()
            return
        try:
            with self.lock:
                cursor = self.state.get('history_id')
                if cursor is None or int(history_id) > int(cursor):
                    self.sync()
                # Acknowledge only after every page and the queue/cursor commit succeed.
                message.ack()
                logging.info('Gmail notification acknowledged; history %s', self.state.get('history_id'))
        except Exception as error:
            logging.warning('Pub/Sub event will retry (%s)', type(error).__name__)
            message.nack()

    def run(self, stop, disconnected):
        from google.cloud import pubsub_v1
        self.sync()  # Catch up after Mac sleep, downtime, or migration from polling.
        with self.lock:
            if self.state.get('pubsub_topic') != self.config['topic'] or time.time() >= float(self.state.get('watch_renew_at', 0)):
                self.renew()
        future = self.subscriber.subscribe(self.config['subscription'], callback=self.notify,
                                          flow_control=pubsub_v1.types.FlowControl(max_messages=10),
                                          await_callbacks_on_shutdown=True)
        try:
            while not stop.wait(60):
                if disconnected():
                    raise RuntimeError('Codex app server disconnected')
                if future.done():
                    future.result()
                    raise RuntimeError('Pub/Sub stream closed')
                with self.lock:
                    now = time.time()
                    if now >= float(self.state.get('watch_renew_at', 0)):
                        self.renew()
                    # Recovery only: Gmail can drop notifications. No 30-second searches.
                    if now - float(self.state.get('last_history_sync', 0)) >= 3600:
                        self.sync()
        finally:
            future.cancel()
            try:
                future.result(timeout=65)
            finally:
                self.subscriber.close()
                self.gmail.session.close()
