from __future__ import annotations

from shared.content_contract import review_key
from ..core.coercion import positive_int


class ReviewSettingsService:
    def __init__(self, config_repository, editorial_profile_repository, transaction):
        self._config_repository = config_repository
        self._editorial_profile_repository = editorial_profile_repository
        self._transaction = transaction

    def get_config(self, content_kind: str = "news") -> dict:
        repo = self._config_repository()
        profile = self._editorial_profile_repository().get_default(content_kind)
        return {
            "prompt": (profile or {}).get("review_prompt") or "",
            "hours": positive_int(repo.get_config(review_key(content_kind, "hours")), 8),
            "kind": content_kind,
            "profile_slug": (profile or {}).get("slug"),
        }

    def set_config(self, prompt: str | None, hours: int | None, content_kind: str = "news") -> dict:
        with self._transaction() as repos:
            if prompt is not None:
                profiles = repos.editorial_profiles
                profile = profiles.get_default(content_kind)
                if not profile:
                    raise RuntimeError(f"没有为 {content_kind} 配置可用的内容档案")
                profiles.save({**profile, "review_prompt": prompt})
            if hours is not None:
                repos.config.set_config(review_key(content_kind, "hours"), str(hours))
        return {"message": "配置已保存"}
