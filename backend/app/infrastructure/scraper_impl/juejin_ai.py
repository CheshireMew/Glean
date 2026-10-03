from datetime import datetime, timezone

from .base import BaseScraper


class JuejinAIScraper(BaseScraper):
    """AI category recommendations; 200 is recommended, 300 is newest."""

    transport_kind = "api"
    allow_empty_results = True
    api_url = "https://api.juejin.cn/recommend_api/v1/article/recommend_cate_feed"
    category_id = "6809637773935378440"

    def __init__(self):
        super().__init__("掘金 · AI 推荐", "https://juejin.cn/ai", 20)
        self.news_type = "article"
        self.front_page_entries = self.front_page_items = None

    async def scrape_important_news(self) -> list[dict]:
        self.front_page_entries = self.front_page_items = None
        payload = await self.transport.fetch_json(self.api_url, method="POST", json_body={
            "id_type": 2, "sort_type": 200, "cate_id": self.category_id,
            "cursor": "0", "limit": min(self.max_items, 20),
        })
        items = self.parse_recommendations(payload)[:self.max_items]
        self.front_page_entries = [{"story_url": item["url"], "source_url": item["url"]} for item in items]
        self.front_page_items = items
        results = self.create_result_buffer()
        for item in items:
            if self.incremental_mode and (item["url"] in self.existing_urls or item["url"] == self.last_news_url):
                continue
            results.append(item)
        return results

    def parse_recommendations(self, payload: dict) -> list[dict]:
        if not isinstance(payload, dict) or payload.get("err_no") != 0 or not isinstance(payload.get("data"), list):
            raise RuntimeError("掘金 AI 推荐接口未返回有效列表，保留上次内容")
        items, seen = [], set()
        for entry in payload["data"]:
            data = entry.get("item_info", entry)
            article = data.get("article_info", {})
            # Non-article cards such as ads are not entries in the article feed.
            if entry.get("item_type", 2) != 2:
                continue
            identifier = str(article.get("article_id", ""))
            title = article.get("title", "").strip()
            if not identifier.isdigit() or not title or str(article.get("category_id")) != self.category_id:
                raise RuntimeError("掘金 AI 推荐条目格式或分类已变化，保留上次内容")
            if identifier in seen:
                continue
            seen.add(identifier)
            try:
                published = datetime.fromtimestamp(int(article["ctime"]), tz=timezone.utc).isoformat()
            except (KeyError, ValueError, OverflowError, OSError):
                raise RuntimeError("掘金 AI 推荐条目缺少有效发布时间") from None
            items.append({"title": title, "content": article.get("brief_content") or "",
                          "url": f"https://juejin.cn/post/{identifier}", "published_at": published,
                          "source_site": self.site_name, "type": "article",
                          "author": data.get("author_user_info", {}).get("user_name") or self.site_name})
        if not items:
            raise RuntimeError("掘金 AI 推荐列表为空，保留上次内容")
        return items
