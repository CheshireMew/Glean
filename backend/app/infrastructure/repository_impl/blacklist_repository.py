from __future__ import annotations

import re
import sqlite3
from typing import Dict, List

from .base_repository import BaseRepository


class BlacklistRepository(BaseRepository):
    def add_blacklist_keyword(self, keyword: str, match_type: str = "contains", content_type: str = "news") -> bool:
        try:
            self.execute(
                "INSERT INTO keyword_blacklist (keyword, match_type, type) VALUES (?, ?, ?)",
                (keyword, match_type, content_type),
            )
            return True
        except sqlite3.IntegrityError:
            return False

    def remove_blacklist_keyword(self, blacklist_id: int) -> bool:
        cursor = self.execute("DELETE FROM keyword_blacklist WHERE id = ?", (blacklist_id,))
        return cursor.rowcount > 0

    def get_blacklist_keywords(self, content_type: str = "news") -> List[Dict]:
        cursor = self.execute(
            "SELECT id, keyword, match_type, type, created_at FROM keyword_blacklist WHERE type = ? ORDER BY created_at DESC",
            (content_type,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def match_keyword(self, text_to_check: str, keywords: List[Dict]) -> str | None:
        for keyword_item in keywords:
            keyword = keyword_item["keyword"]
            match_type = keyword_item.get("match_type", "contains")
            if match_type == "regex":
                try:
                    if re.search(keyword, text_to_check, re.IGNORECASE):
                        return f"正则:{keyword}"
                except re.error:
                    continue
            elif keyword.lower() in text_to_check:
                return f"包含:{keyword}"
        return None
