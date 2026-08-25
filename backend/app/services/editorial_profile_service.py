from __future__ import annotations

import re
from typing import Dict

from shared.content_contract import CONTENT_KINDS

from ..core.exceptions import ValidationError


class EditorialProfileService:
    def __init__(self, editorial_profile_repository, publication_repository, transaction):
        self._editorial_profile_repository = editorial_profile_repository
        self._publication_repository = publication_repository
        self._transaction = transaction

    def list_profiles(self, content_kind: str | None = None) -> Dict:
        if content_kind and content_kind not in CONTENT_KINDS:
            raise ValidationError("内容类型无效")
        return {"profiles": self._editorial_profile_repository().list_profiles(content_kind)}

    def save_profile(self, payload: Dict) -> Dict:
        slug = (payload.get("slug") or "").strip().lower()
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            raise ValidationError("内容档案标识只能包含小写字母、数字和连字符")
        if payload.get("content_type") not in CONTENT_KINDS:
            raise ValidationError("内容类型无效")
        if not (payload.get("name") or "").strip():
            raise ValidationError("内容档案名称不能为空")
        if payload.get("enabled", True) and not (payload.get("review_prompt") or "").strip():
            raise ValidationError("启用内容档案前必须填写审核标准")
        if payload.get("is_default") and not payload.get("enabled", True):
            raise ValidationError("默认内容档案必须保持启用")
        normalized = {**payload, "slug": slug, "name": payload["name"].strip()}
        with self._transaction() as tx_repos:
            existing = tx_repos.editorial_profiles.get(slug)
            if existing and existing.get("is_default") and (
                not normalized.get("is_default")
                or not normalized.get("enabled")
                or normalized.get("content_type") != existing.get("content_type")
            ):
                raise ValidationError("不能直接取消、停用或改动当前默认档案；请先把同类的另一个档案设为默认")
            current_default = tx_repos.editorial_profiles.get_default(normalized["content_type"])
            if normalized.get("enabled") and not normalized.get("is_default") and not current_default:
                raise ValidationError("该内容类型还没有默认档案，请将此档案设为默认")
            saved = tx_repos.editorial_profiles.save(normalized)
            tx_repos.publications.ensure_for_profile(saved)
            return saved
