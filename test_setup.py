import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from appy_config import setting, tracker_id
from setup_workspace import initialize

ROOT = Path(__file__).resolve().parent


class SetupTests(unittest.TestCase):
    def setUp(self):
        (ROOT / 'tmp').mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=ROOT / 'tmp')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_initialize_preserves_existing_private_data(self):
        shutil.copytree(ROOT / 'templates', self.root / 'templates')
        shutil.copy(ROOT / '.env.example', self.root / '.env.example')
        initialize(self.root)
        profile = self.root / 'INFORMATION.md'
        profile.write_text('Existing private profile')
        self.assertEqual(initialize(self.root), [])
        self.assertEqual(profile.read_text(), 'Existing private profile')
        self.assertEqual((self.root / '.env').stat().st_mode & 0o777, 0o600)

    def test_settings_never_execute_shell_and_honor_environment(self):
        env = self.root / '.env'
        env.write_text('export APPY_TEST="$(echo secret)" # literal\n')
        self.assertEqual(setting('APPY_TEST', env), '$(echo secret)')
        with patch.dict(os.environ, {'APPY_TEST': 'override'}):
            self.assertEqual(setting('APPY_TEST', env), 'override')

    def test_tracker_rejects_unconfigured_and_accepts_user_data_source(self):
        with patch('appy_config.setting', return_value=''):
            with self.assertRaisesRegex(RuntimeError, 'NOTION_TRACKER_ID'):
                tracker_id()
        expected = 'collection://11111111-1111-4111-8111-111111111111'
        with patch('appy_config.setting', return_value=expected):
            self.assertEqual(tracker_id(), expected)
