from typing import List, Optional

from .base_repository import BaseRepository


class TagRepository(BaseRepository):
    def get_tag(self, tag_id: int):
        row = self.execute(
            """
            SELECT t.*, COUNT(nt.news_id) AS usage_count
            FROM tags t LEFT JOIN news_tags nt ON nt.tag_id = t.id
            WHERE t.id = ? GROUP BY t.id
            """,
            (tag_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_tags(self) -> list[dict]:
        rows = self.execute(
            """
            SELECT t.*, COUNT(nt.news_id) AS usage_count
            FROM tags t LEFT JOIN news_tags nt ON nt.tag_id = t.id
            GROUP BY t.id ORDER BY usage_count DESC, t.name
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def insert_or_get_tag(self, tag_name: str, category: Optional[str] = None) -> int:
        cursor = self.execute('SELECT id FROM tags WHERE name = ?', (tag_name,))
        row = cursor.fetchone()
        if row:
            return int(row['id'])

        cursor = self.execute('INSERT INTO tags (name, category) VALUES (?, ?)', (tag_name, category))
        return int(cursor.lastrowid)

    def associate_tags(self, news_id: int, tag_ids: List[int]) -> None:
        for tag_id in tag_ids:
            self.execute(
                'INSERT OR IGNORE INTO news_tags (news_id, tag_id) VALUES (?, ?)',
                (news_id, tag_id),
            )
