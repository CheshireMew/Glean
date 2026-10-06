from __future__ import annotations

import json
import sqlite3


def protected_review_sql(alias: str) -> str:
    return f'''(
        EXISTS (SELECT 1 FROM publication_draft_items i JOIN publication_drafts d ON d.id=i.draft_id
            WHERE i.review_entry_id={alias}.id AND d.status IN ('draft','scheduled','publishing'))
        OR EXISTS (SELECT 1 FROM delivery_operation_entries e
            JOIN delivery_operations o ON o.id=e.operation_id
            JOIN delivery_plans p ON json_extract(o.metadata, '$.plan_key')=p.plan_key
            WHERE e.review_entry_id={alias}.id AND p.finalized_at IS NULL)
    )'''


def migrate_draft_retention(cursor: sqlite3.Cursor) -> None:
    columns = {row[1] for row in cursor.execute('PRAGMA table_info(publication_draft_items)').fetchall()}
    if 'snapshot_json' not in columns:
        cursor.execute('ALTER TABLE publication_draft_items RENAME TO publication_draft_items_before_snapshots')
        cursor.execute('''
            CREATE TABLE publication_draft_items (
                draft_id INTEGER NOT NULL,
                review_entry_id INTEGER,
                position INTEGER NOT NULL,
                section TEXT NOT NULL DEFAULT '其他',
                included BOOLEAN NOT NULL DEFAULT 1,
                overrides_json TEXT NOT NULL DEFAULT '{}',
                snapshot_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY (draft_id, position),
                UNIQUE (draft_id, review_entry_id),
                FOREIGN KEY (draft_id) REFERENCES publication_drafts(id) ON DELETE CASCADE,
                FOREIGN KEY (review_entry_id) REFERENCES review_entries(id) ON DELETE SET NULL,
                CHECK (position >= 0), CHECK (included IN (0,1))
            )
        ''')
        cursor.execute('''
            INSERT INTO publication_draft_items(draft_id,review_entry_id,position,section,included,overrides_json)
            SELECT draft_id,review_entry_id,position,section,included,overrides_json
            FROM publication_draft_items_before_snapshots
        ''')
        cursor.execute('DROP TABLE publication_draft_items_before_snapshots')
    # Publication writes the exact accepted snapshot. For legacy drafts, recover
    # available published report facts before falling back to the retained entry.
    rows = cursor.execute('''
        SELECT i.draft_id, i.review_entry_id, d.published_report_id, p.profile_slug
        FROM publication_draft_items i JOIN publication_drafts d ON d.id=i.draft_id
        JOIN profile_publications p ON p.id=d.publication_id
        WHERE d.status='published' AND i.snapshot_json='{}' AND d.published_report_id IS NOT NULL
    ''').fetchall()
    for draft_id, review_id, report_id, profile_slug in rows:
        row = cursor.execute('SELECT * FROM daily_report_items WHERE report_id=? AND review_entry_id=?', (report_id, review_id)).fetchone()
        if row:
            snapshot = dict(zip((column[0] for column in cursor.description), row))
            snapshot.update(original_review_entry_id=review_id, profile_slug=profile_slug)
            # Report item identity is separate from the original review identity.
            snapshot.pop('id', None)
            cursor.execute('UPDATE publication_draft_items SET snapshot_json=? WHERE draft_id=? AND review_entry_id=?',
                           (json.dumps(snapshot, ensure_ascii=False), draft_id, review_id))
    fields = ('title', 'source_site', 'source_url', 'published_at', 'content_type',
              'review_summary', 'enriched_summary', 'enriched_impact', 'enriched_background',
              'enrichment_citations', 'event_id')
    pairs = ','.join(f"'{name}', OLD.{name}" for name in fields)
    cursor.execute(f'''
        CREATE TRIGGER IF NOT EXISTS preserve_draft_snapshot_before_review_delete
        BEFORE DELETE ON review_entries BEGIN
            SELECT CASE WHEN {protected_review_sql('OLD')}
                THEN RAISE(ABORT, 'content_has_active_editorial_reference') END;
            UPDATE publication_draft_items SET snapshot_json=json_object({pairs},
                'original_review_entry_id', OLD.id, 'profile_slug', OLD.profile_slug)
            WHERE review_entry_id=OLD.id AND snapshot_json='{{}}';
        END
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_draft_items_review ON publication_draft_items(review_entry_id)')


def create_delivery_and_retention_schema(cursor: sqlite3.Cursor) -> None:
    from .delivery_plan_schema import create_delivery_plan_schema
    from .sqlite_schema import create_public_revision_tracking

    create_delivery_plan_schema(cursor)
    migrate_draft_retention(cursor)
    create_public_revision_tracking(cursor)
