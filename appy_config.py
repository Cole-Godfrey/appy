"""Read local settings without executing shell code or exposing credentials."""
import os
from pathlib import Path
import re
import shlex

ROOT = Path(__file__).resolve().parent


def setting(name, path=None):
    if name in os.environ:
        return os.environ[name].strip()
    path = Path(path) if path is not None else ROOT / '.env'
    if not path.exists():
        return ''
    for line in path.read_text().splitlines():
        key, separator, value = line.strip().removeprefix('export ').partition('=')
        if separator and key.strip() == name:
            parts = shlex.split(value, comments=True)
            if len(parts) > 1:
                raise ValueError('Invalid setting: ' + name)
            return parts[0] if parts else ''
    return ''


def tracker_id():
    value = setting('NOTION_TRACKER_ID')
    if not re.fullmatch(r'collection://[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', value):
        raise RuntimeError('Set NOTION_TRACKER_ID to your collection:// data source ID in .env')
    return value
