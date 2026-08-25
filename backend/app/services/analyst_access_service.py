from __future__ import annotations

import secrets
from typing import Dict, List, Optional

from ..core.exceptions import AuthenticationError, NotFoundError


class AnalystAccessService:
    def __init__(self, api_key_repository):
        self._api_key_repository = api_key_repository

    def get_api_keys(self) -> List[Dict]:
        return self._api_key_repository().get_analyst_api_keys()

    def authenticate(self, api_key: str) -> Dict:
        result = self._api_key_repository().authenticate(api_key)
        if not result:
            raise AuthenticationError("分析师 API 密钥无效或已停用")
        return result

    async def create_api_key(self, key_name: str, notes: Optional[str]) -> Dict:
        api_key = f"analyst_{secrets.token_urlsafe(24)}"
        key_id = self._api_key_repository().create_analyst_api_key(key_name, api_key, notes)
        return {
            "id": key_id,
            "api_key": api_key,
            "key_name": key_name,
            "notes": notes,
            "message": "API Key 创建成功",
        }

    def set_api_key_enabled(self, key_id: int, enabled: bool) -> Dict:
        if not self._api_key_repository().set_enabled(key_id, enabled):
            raise NotFoundError("API Key 不存在")
        return {"message": "API Key 状态已更新"}

    async def delete_api_key(self, key_id: int) -> Dict:
        if not self._api_key_repository().delete_analyst_api_key(key_id):
            raise NotFoundError("API Key 不存在")
        return {"message": "API Key 删除成功"}
