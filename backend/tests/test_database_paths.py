from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.app.infrastructure.sqlite.db_sqlite import Database


class DatabasePathTest(unittest.TestCase):
    def setUp(self):
        Path(r"D:\Tools").mkdir(parents=True, exist_ok=True)
        self.temp_dir = tempfile.TemporaryDirectory(dir=r"D:\Tools")
        self.root = Path(self.temp_dir.name)
        self.root_patch = patch("backend.app.infrastructure.sqlite.db_sqlite.PROJECT_ROOT", self.root)
        self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop()
        self.temp_dir.cleanup()

    def test_new_install_uses_data_directory(self):
        db = Database()
        self.assertEqual(Path(db.db_path), self.root / "data" / "ainews.db")
        db.init_db()
        self.assertTrue(Path(db.db_path).is_file())
        self.assertFalse((self.root / "ainews.db").exists())

    def test_old_install_keeps_existing_database(self):
        original = self.root / "ainews.db"
        original.write_bytes(b"existing database marker")
        db = Database()
        self.assertEqual(Path(db.db_path), original)
        self.assertEqual(original.read_bytes(), b"existing database marker")
        self.assertFalse((self.root / "data").exists())

    def test_two_existing_databases_are_not_selected_silently(self):
        current = self.root / "data" / "ainews.db"
        current.parent.mkdir()
        current.write_bytes(b"current")
        legacy = self.root / "ainews.db"
        legacy.write_bytes(b"legacy")
        with self.assertRaisesRegex(RuntimeError, "同时存在"):
            Database()
        self.assertEqual(current.read_bytes(), b"current")
        self.assertEqual(legacy.read_bytes(), b"legacy")

    def test_explicit_path_is_preserved(self):
        explicit = self.root / "custom.db"
        db = Database(str(explicit))
        self.assertEqual(db.db_path, str(explicit))
        self.assertFalse((self.root / "data").exists())
