from __future__ import annotations

import sqlite3


def create_delivery_plan_schema(cursor: sqlite3.Cursor) -> None:
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS delivery_plans (
            plan_key TEXT PRIMARY KEY,
            operation_type TEXT NOT NULL,
            owner_id INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            operation_keys_json TEXT NOT NULL,
            result_json TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finalized_at TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_delivery_plans_owner
        ON delivery_plans(operation_type, owner_id, finalized_at)
    ''')
