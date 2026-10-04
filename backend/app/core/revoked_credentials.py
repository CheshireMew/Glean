"""Reject credentials previously committed to this repository; no plaintext values."""
import hashlib
import json
from pathlib import Path

REVOKED = json.loads(Path(__file__).with_name('revoked_credentials.json').read_text(encoding='utf-8'))


def is_revoked(kind, value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest() in REVOKED.get(kind, [])
