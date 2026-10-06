from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import sqlite3
import subprocess
import types
import unittest
from unittest.mock import patch
import uuid

from backend.app.infrastructure.sqlite import sqlite_migration_plan as current
from backend.app.infrastructure.sqlite.db_sqlite import Database
from backend.tests import test_editorial_integrity as fixture


class DeliveryPlanMigrationTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(os.environ.get('GLEAN_TEST_EVIDENCE_ROOT', r'D:\Tools\CodexAudits\Glean\migration-tests')) / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self.path = self.root / 'old.db'
        # Exact registered old schema producer, read from the audited Git object.
        result = subprocess.run(['git', 'show', '426283170f379ae70251ff206c3233363725a329:backend/app/infrastructure/sqlite/sqlite_migration_plan.py'],
                                cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, encoding='utf-8', check=True)
        module = types.ModuleType('backend.app.infrastructure.sqlite.audit_old_plan')
        module.__package__ = 'backend.app.infrastructure.sqlite'
        import sys
        sys.modules[module.__name__] = module
        exec(compile(result.stdout, 'audited-old-migration-plan', 'exec'), module.__dict__)
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            module.create_current_schema(conn.cursor())
            conn.execute('CREATE TABLE schema_migrations(version TEXT PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
            conn.execute('INSERT INTO schema_migrations(version) VALUES (?)', (module.SCHEMA_VERSION,))
            obj = types.SimpleNamespace(conn=conn)
            entry, _, _ = fixture.EditorialIntegrityTest.seed_entry(obj, 'daily-briefs', 'news', 'migration original')
            publication = conn.execute("SELECT id FROM profile_publications WHERE profile_slug='daily-briefs'").fetchone()[0]
            conn.execute("INSERT INTO publication_drafts(draft_key,publication_id,content_type,title,created_by) VALUES ('migration',?,'news','old draft','editor')", (publication,))
            conn.execute("INSERT INTO publication_draft_items(draft_id,review_entry_id,position) VALUES (1,?,0)", (entry,))
        self.db = Database(str(self.path))

    def test_real_old_schema_migrates_and_reopens_without_losing_draft_items(self):
        self.db.init_db()
        self.db.init_db()
        with self.db.connect() as conn:
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM publication_draft_items').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT snapshot_json FROM publication_draft_items').fetchone()[0], '{}')
            self.assertIsNotNone(conn.execute("SELECT name FROM sqlite_master WHERE name='delivery_plans'").fetchone())
            self.assertEqual(conn.execute('SELECT version FROM schema_migrations ORDER BY applied_at DESC,version DESC').fetchone()[0], current.SCHEMA_VERSION)
        backups = list((self.root / 'backups').iterdir())
        self.assertEqual(len(backups), 1)
        with sqlite3.connect(backups[0]) as conn:
            self.assertEqual(conn.execute('SELECT version FROM schema_migrations').fetchone()[0], '2026.10.03.1')

    def test_failed_upgrade_rolls_back_structure_and_can_resume_from_same_database(self):
        original = current.resolve_migration_plan('2026.10.03.1')[0]

        def fail_after_rebuild(cursor):
            original.apply(cursor)
            raise RuntimeError('controlled migration interruption')

        failed = replace(original, apply=fail_after_rebuild)
        with patch('backend.app.infrastructure.sqlite.db_sqlite.resolve_migration_plan', return_value=(failed,)):
            with self.assertRaisesRegex(RuntimeError, 'controlled migration interruption'):
                self.db.init_db()
        with self.db.connect() as conn:
            self.assertEqual(conn.execute('SELECT version FROM schema_migrations').fetchone()[0], '2026.10.03.1')
            self.assertNotIn('snapshot_json', {row[1] for row in conn.execute('PRAGMA table_info(publication_draft_items)')})
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM publication_draft_items').fetchone()[0], 1)
            self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE name='delivery_plans'").fetchone())
        self.db.init_db()
        self.db.assert_schema_current()
