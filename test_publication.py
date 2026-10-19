import unittest

from scripts.check_public import audit


class PublicationTests(unittest.TestCase):
    def test_private_records_cannot_be_published_even_if_force_added(self):
        for name in ['INFORMATION.md', 'private/resume.pdf', 'nested/IMPROVEMENTS.md',
                     '.env.production', 'gmail-token.json', 'tmp/tracker.json']:
            self.assertIn('private file', audit(name, ''))

    def test_templates_and_synthetic_fixtures_are_allowed(self):
        self.assertEqual(audit('templates/INFORMATION.md', '- Email: you@example.com'), [])
        self.assertEqual(audit('.env.example', 'NOTION_TRACKER_ID=\n'), [])

    def test_detection_does_not_echo_sensitive_values(self):
        value = 'ghp_' + 'a' * 36
        self.assertEqual(audit('example.txt', value), ['credential-like value'])
