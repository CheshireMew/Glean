from __future__ import annotations

from typing import Dict, Iterable

from .ai_runtime import ResilientAIClient


class EditorialAIService:
    def __init__(
        self,
        providers: Iterable[Dict],
        concurrency: int,
        throttle_seconds: float = 0.0,
        telemetry_observer=None,
    ):
        self.client = ResilientAIClient(
            providers, concurrency, throttle_seconds, telemetry_observer
        )

    async def review_event(
        self,
        title: str,
        review_prompt: str,
        content: str = "",
        telemetry_context: Dict | None = None,
    ) -> Dict:
        system_prompt = """
你是新闻审核助手。请基于用户给出的偏好判断内容是否应该进入精选输出。

只返回 JSON 对象，字段如下：
{
  "passed": true,
  "score": 8,
  "reason": "一句中文短理由",
  "category": "一句中文分类",
  "summary": "一句中文摘要"
}

要求：
1. score 为 1-10 的整数
2. passed 为 true 表示应保留，为 false 表示应丢弃
3. 不要输出任何 JSON 之外的内容
"""
        user_prompt = f"""审核偏好：
{review_prompt}

标题：
{title}

正文摘要：
{content[:1200]}
"""
        parsed = await self.client.complete_json(
            system=system_prompt,
            user=user_prompt,
            temperature=0.2,
            max_tokens=300,
            context={"stage": "review", **(telemetry_context or {})},
        )
        return {
            "passed": bool(parsed.get("passed", False)),
            "score": int(parsed.get("score", 0) or 0),
            "reason": str(parsed.get("reason", "") or ""),
            "category": str(parsed.get("category", "") or ""),
            "summary": str(parsed.get("summary", "") or ""),
        }

    async def enrich_event(
        self,
        title: str,
        sources: list[Dict],
        enrichment_prompt: str,
        telemetry_context: Dict | None = None,
    ) -> Dict:
        source_blocks = []
        allowed_ids = set()
        source_map = {}
        for source in sources:
            source_id = int(source["id"])
            allowed_ids.add(source_id)
            source_map[source_id] = {
                "news_id": source_id,
                "title": source["title"],
                "source_site": source["source_site"],
                "source_url": source["source_url"],
            }
            source_blocks.append(
                f"[来源 {source_id}] {source['source_site']}\n标题：{source['title']}\n正文：{(source.get('content') or '')[:1400]}"
            )
        parsed = await self.client.complete_json(
            system=(
                "你是新闻研究编辑。只能使用给定来源中的事实，不得补写未提供的事实。"
                "返回 JSON：summary、why_it_matters、background、citation_ids。"
                "citation_ids 必须只包含实际支撑文字的来源编号；没有依据时相应字段留空。"
            ),
            user=f"编辑要求：{enrichment_prompt}\n\n事件：{title}\n\n" + "\n\n".join(source_blocks),
            temperature=0.1,
            max_tokens=900,
            context={"stage": "enrichment", **(telemetry_context or {})},
        )
        citation_ids = []
        for value in parsed.get("citation_ids") or []:
            try:
                source_id = int(value)
            except Exception:
                continue
            if source_id in allowed_ids and source_id not in citation_ids:
                citation_ids.append(source_id)
        return {
            "summary": str(parsed.get("summary") or ""),
            "why_it_matters": str(parsed.get("why_it_matters") or ""),
            "background": str(parsed.get("background") or ""),
            "citations": [source_map[source_id] for source_id in citation_ids],
        }

    async def test_connection(self):
        try:
            await self.client.complete_json(
                system="只返回 JSON。",
                user='返回 {"ok": true}',
                temperature=0,
                max_tokens=20,
                context={"stage": "connection_test"},
            )
            return {"ok": True, "message": "连接成功"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    async def close(self) -> None:
        await self.client.close()
