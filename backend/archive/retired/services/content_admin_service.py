from __future__ import annotations

from typing import Dict, List, Optional
import secrets

from ..core.exceptions import BusinessError, NotFoundError
from ..infrastructure.repositories import repositories


class ContentAdminService:
    @staticmethod
    def _repos():
        return repositories()

    def get_blacklist(self, content_kind: str = "news") -> Dict:
        return {"keywords": self._repos().blacklist.get_blacklist_keywords(content_kind)}

    def add_blacklist(self, keyword: str, match_type: str, content_kind: str) -> Dict:
        success = self._repos().blacklist.add_blacklist_keyword(keyword, match_type, content_kind)
        if not success:
            raise BusinessError("添加失败，可能关键词已存在")
        return {"message": "添加成功"}

    def delete_blacklist(self, blacklist_id: int) -> Dict:
        success = self._repos().blacklist.remove_blacklist_keyword(blacklist_id)
        if not success:
            raise NotFoundError("删除失败")
        return {"message": "删除成功"}

    def export_review_results(self, hours: int, min_score: int, content_kind: str = "news") -> Dict:
        return self._repos().review_admin.export_selected_entries(hours, min_score, content_kind)

    def get_analyst_api_keys(self) -> List[Dict]:
        return self._repos().api_keys.get_analyst_api_keys()

    async def create_analyst_api_key(self, key_name: str, notes: Optional[str]) -> Dict:
        api_key = f"analyst_{secrets.token_urlsafe(24)}"
        key_id = self._repos().api_keys.create_analyst_api_key(key_name, api_key, notes)
        return {"id": key_id, "api_key": api_key, "key_name": key_name, "notes": notes, "message": "API Key 创建成功"}

    async def delete_analyst_api_key(self, key_id: int) -> Dict:
        deleted = self._repos().api_keys.delete_analyst_api_key(key_id)
        if not deleted:
            raise NotFoundError("API Key 不存在")
        return {"message": "API Key 删除成功"}


content_admin_service = ContentAdminService()
