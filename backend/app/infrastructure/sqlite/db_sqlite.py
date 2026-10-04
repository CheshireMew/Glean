"""SQLite 数据库实现。"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from logging import getLogger
from pathlib import Path

from shared.db_base import DatabaseBase

from .sqlite_migration_plan import (
    SCHEMA_VERSION,
    create_current_schema,
    resolve_migration_plan,
)
logger = getLogger("glean.database")
PROJECT_ROOT = Path(__file__).resolve().parents[4]


def default_database_path(project_root: Path) -> Path:
    current = project_root / "data" / "ainews.db"
    legacy = project_root / "ainews.db"
    if current.exists() and legacy.exists():
        raise RuntimeError("data/ainews.db 与根目录 ainews.db 同时存在，请先确认需要使用的数据库")
    # Older checkouts keep using their existing database until it is moved explicitly.
    return legacy if legacy.exists() else current


class Database(DatabaseBase):
    def __init__(self, db_path: str | None = None):
        if db_path is None:
            selected = default_database_path(PROJECT_ROOT)
            selected.parent.mkdir(parents=True, exist_ok=True)
            db_path = str(selected)
        self.db_path = db_path

    def connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA busy_timeout=30000;")
        return conn

    def init_db(self):
        if self._read_schema_version() == SCHEMA_VERSION:
            return
        with self._migration_lock():
            self._init_db_locked()

    def _init_db_locked(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA busy_timeout=30000;")
        cursor = conn.cursor()
        try:
            previous_version = self._current_schema_version(cursor)
            if previous_version == SCHEMA_VERSION:
                return
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
            except Exception:
                pass
            has_application_tables = self._has_application_tables(cursor)
            if not has_application_tables:
                conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
            migration_plan = resolve_migration_plan(previous_version) if has_application_tables else ()
            if has_application_tables:
                backup_path = self._backup_database(conn, previous_version)
                logger.info(
                    "Created pre-migration database backup path=%s from_version=%s to_version=%s",
                    backup_path,
                    previous_version or "unversioned",
                    SCHEMA_VERSION,
                )
            # Schema rebuilds keep child rows intact and retain references to the canonical
            # table names. Integrity is checked before the migration is committed.
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute("PRAGMA legacy_alter_table=ON")
            conn.execute("BEGIN IMMEDIATE")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            if not has_application_tables:
                create_current_schema(cursor)
                cursor.execute(
                    "INSERT OR IGNORE INTO schema_migrations (version) VALUES (?)",
                    (SCHEMA_VERSION,),
                )
            else:
                for step in migration_plan:
                    step.apply(cursor)
                    cursor.execute(
                        "INSERT OR IGNORE INTO schema_migrations (version) VALUES (?)",
                        (step.to_version,),
                    )
            violations = cursor.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                first = tuple(violations[0])
                raise RuntimeError(f"数据库迁移后存在外键异常：{first}，共 {len(violations)} 条")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.execute("PRAGMA legacy_alter_table=OFF")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.close()

    def _read_schema_version(self) -> str | None:
        db_path = Path(self.db_path)
        if not db_path.exists():
            return None
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            return self._current_schema_version(conn.cursor())
        finally:
            conn.close()

    @contextmanager
    def _migration_lock(self):
        """Serialize schema inspection, backup and migration across API processes on Windows."""
        import os

        lock_path = Path(f"{self.db_path}.migration.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as handle:
            handle.seek(0)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == 'nt':
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def assert_schema_current(self) -> None:
        conn = self.connect()
        try:
            version = self._current_schema_version(conn.cursor())
            if version != SCHEMA_VERSION:
                raise RuntimeError(
                    f"数据库结构尚未就绪：当前 {version or 'unversioned'}，需要 {SCHEMA_VERSION}；"
                    "请先启动 API 或运行 .\\glean.ps1 system init 完成迁移"
                )
        finally:
            conn.close()

    @staticmethod
    def _current_schema_version(cursor: sqlite3.Cursor) -> str | None:
        exists = cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()
        if not exists:
            return None
        row = cursor.execute("SELECT version FROM schema_migrations ORDER BY rowid DESC LIMIT 1").fetchone()
        return row["version"] if row else None

    @staticmethod
    def _has_application_tables(cursor: sqlite3.Cursor) -> bool:
        row = cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' AND name != 'schema_migrations' LIMIT 1"
        ).fetchone()
        return row is not None

    def _backup_database(self, source: sqlite3.Connection, previous_version: str | None) -> Path:
        db_path = Path(self.db_path).resolve()
        backup_dir = db_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        old_label = (previous_version or "unversioned").replace(".", "-")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup_path = backup_dir / f"{db_path.stem}-before-{old_label}-to-{SCHEMA_VERSION.replace('.', '-')}-{timestamp}.db"
        target = sqlite3.connect(backup_path)
        try:
            source.backup(target)
        finally:
            target.close()
        return backup_path
