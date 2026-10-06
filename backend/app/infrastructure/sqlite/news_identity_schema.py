"""Persistent URL identity claims, without deleting historical alias rows."""
from __future__ import annotations

import sqlite3

from ...domain.source_identity import source_identity
from .sqlite_support import ensure_column


def create_news_identity_schema(cursor: sqlite3.Cursor) -> None:
    ensure_column(cursor, 'news', 'source_identity', 'TEXT')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_news_source_identity ON news(source_identity)')
    cursor.execute('''CREATE TABLE IF NOT EXISTS news_source_identities (
        identity TEXT PRIMARY KEY NOT NULL,
        news_id INTEGER NOT NULL REFERENCES news(id) ON DELETE CASCADE
    )''')
    # Retain every source row and ID, including pre-existing aliases referenced by
    # events, archives or drafts. The first row owns the persistent identity claim.
    # An earlier legacy migration may have created rows using raw SQL. Rebuild
    # only identity metadata under the caller's migration transaction, so even
    # these rows use the same canonical identity as current repository writes.
    for name in ('news_identity_before_insert', 'news_identity_after_insert',
                 'news_identity_before_update', 'news_identity_after_update',
                 'news_identity_after_delete', 'news_identity_require_update'):
        cursor.execute(f'DROP TRIGGER IF EXISTS {name}')
    cursor.execute('DELETE FROM news_source_identities')
    rows = cursor.execute('SELECT id, source_url, source_identity FROM news ORDER BY id').fetchall()
    for row in rows:
        identity = source_identity(row[1])
        if row[2] != identity:
            cursor.execute('UPDATE news SET source_identity = ? WHERE id = ?', (identity, row[0]))
    cursor.execute('''INSERT OR IGNORE INTO news_source_identities(identity, news_id)
        SELECT source_identity, MIN(id) FROM news WHERE source_identity IS NOT NULL GROUP BY source_identity''')
    cursor.execute('''CREATE TRIGGER IF NOT EXISTS news_identity_before_insert
        BEFORE INSERT ON news WHEN EXISTS (
            SELECT 1 FROM news_source_identities WHERE identity = COALESCE(NEW.source_identity, NEW.source_url)
        ) BEGIN SELECT RAISE(IGNORE); END''')
    cursor.execute('''CREATE TRIGGER IF NOT EXISTS news_identity_after_insert AFTER INSERT ON news BEGIN
        UPDATE news SET source_identity = COALESCE(NEW.source_identity, NEW.source_url) WHERE id = NEW.id;
        INSERT OR IGNORE INTO news_source_identities(identity, news_id)
            VALUES (COALESCE(NEW.source_identity, NEW.source_url), NEW.id);
    END''')
    cursor.execute('''CREATE TRIGGER IF NOT EXISTS news_identity_before_update
        BEFORE UPDATE OF source_identity ON news WHEN NEW.source_identity IS NOT OLD.source_identity
        AND EXISTS (SELECT 1 FROM news_source_identities
                    WHERE identity = NEW.source_identity AND news_id != OLD.id)
        BEGIN SELECT RAISE(ABORT, 'news_source_identity_conflict'); END''')
    cursor.execute('''CREATE TRIGGER IF NOT EXISTS news_identity_require_update
        BEFORE UPDATE OF source_identity ON news WHEN NEW.source_identity IS NULL
        BEGIN SELECT RAISE(ABORT, 'news_source_identity_required'); END''')
    cursor.execute('''CREATE TRIGGER IF NOT EXISTS news_identity_after_update
        AFTER UPDATE OF source_identity ON news WHEN NEW.source_identity IS NOT OLD.source_identity BEGIN
        DELETE FROM news_source_identities WHERE identity = OLD.source_identity AND news_id = OLD.id;
        INSERT OR IGNORE INTO news_source_identities(identity, news_id)
            SELECT source_identity, MIN(id) FROM news WHERE source_identity = OLD.source_identity GROUP BY source_identity;
        INSERT OR IGNORE INTO news_source_identities(identity, news_id) VALUES (NEW.source_identity, NEW.id);
    END''')
    cursor.execute('''CREATE TRIGGER IF NOT EXISTS news_identity_after_delete AFTER DELETE ON news BEGIN
        DELETE FROM news_source_identities WHERE news_id = OLD.id;
        INSERT OR IGNORE INTO news_source_identities(identity, news_id)
            SELECT source_identity, MIN(id) FROM news WHERE source_identity = OLD.source_identity GROUP BY source_identity;
    END''')
