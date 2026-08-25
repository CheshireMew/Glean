from __future__ import annotations

from typing import Dict
import re

from ..core.exceptions import BusinessError, NotFoundError, ValidationError


class BlacklistService:
    def __init__(self, blacklist_repository):
        self._blacklist_repository = blacklist_repository

    def get_blacklist(self, content_kind: str = "news") -> Dict:
        return {"keywords": self._blacklist_repository().get_blacklist_keywords(content_kind)}

    def add_blacklist(self, keyword: str, match_type: str, content_kind: str) -> Dict:
        normalized = keyword.strip()
        if not normalized:
            raise ValidationError("黑名单关键词不能为空")
        if match_type == "regex":
            try:
                re.compile(normalized)
            except re.error as exc:
                raise ValidationError(f"正则表达式无效: {exc}") from exc
        success = self._blacklist_repository().add_blacklist_keyword(normalized, match_type, content_kind)
        if not success:
            raise BusinessError("添加失败，可能关键词已存在")
        return {"message": "添加成功"}

    def delete_blacklist(self, blacklist_id: int) -> Dict:
        success = self._blacklist_repository().remove_blacklist_keyword(blacklist_id)
        if not success:
            raise NotFoundError("删除失败")
        return {"message": "删除成功"}
