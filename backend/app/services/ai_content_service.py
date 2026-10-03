from __future__ import annotations

from ..core.exceptions import ValidationError
from ..domain.ai_sources import PUBLIC_AI_SOURCES, source_text
from ..domain.wechat import wechat_runtime_name, wechat_source_name


class AIContentService:
    def __init__(self, repository, rss_repository, wechat_repository=None):
        self._repository = repository
        self._rss_repository = rss_repository
        self._wechat_repository = wechat_repository

    def get_content(self, source: str | None, query: str, limit: int, offset: int) -> dict:
        definitions = list(PUBLIC_AI_SOURCES)
        if self._wechat_repository:
            definitions.extend({'key': wechat_runtime_name(row['id']), 'name': wechat_source_name(row['name']),
                                'rss_slug': None, 'site_url': 'https://mp.weixin.qq.com/'}
                               for row in self._wechat_repository().list_sources(enabled_only=True))
        if source and source not in {item["key"] for item in definitions}:
            raise ValidationError("未知 AI 资讯来源")
        configured = {item["slug"]: item for item in self._rss_repository().list_sources()}
        sources = []
        names_by_key = {}
        for definition in definitions:
            config = configured.get(definition["rss_slug"], {})
            names = list(dict.fromkeys([definition["name"], config.get("display_name") or definition["name"]]))
            names_by_key[definition["key"]] = names
            sources.append({
                "key": definition["key"], "name": config.get("display_name") or definition["name"],
                "site_url": config.get("site_url") or definition["site_url"],
                **self._repository().source_stats(names),
            })
        name_to_key = {name: key for key, names in names_by_key.items() for name in names}
        selected_names = names_by_key[source] if source else list(name_to_key)
        result = self._repository().list_items(selected_names, query.strip(), limit, offset)
        for item in result["items"]:
            item["source_key"] = name_to_key[item["source_site"]]
            item["source_excerpt"] = source_text(item["source_key"], item["title"], item.pop("content"))
            item["original_title"] = item["title"]
            title_zh, excerpt_zh = item.pop("title_zh"), item.pop("excerpt_zh")
            item["translated"] = bool(title_zh or excerpt_zh)
            item["title"] = title_zh or item["title"]
            item["source_excerpt"] = excerpt_zh or item["source_excerpt"]
        result["sources"] = sources
        return result
