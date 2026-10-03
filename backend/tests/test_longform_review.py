from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

from backend.app.services.llm import EditorialAIService


class LongformReviewTest(IsolatedAsyncioTestCase):
    def make_service(self, client):
        with patch("backend.app.services.llm.ResilientAIClient", return_value=client):
            return EditorialAIService([], 1)

    async def test_review_receives_middle_and_ending_without_changing_preferences(self):
        content = "开头的背景。\n" * 300 + "中段证据：实验结果与先前假设不同。\n" + "实验过程。\n" * 1800 + "结论：现有证据不支持推广。"
        preference = "保留有实验依据的实践文章"
        decision = {"passed": True, "score": 8, "reason": "有实验依据", "category": "实践", "summary": "实验未支持推广"}
        client = Mock(complete_json=AsyncMock(return_value=decision))
        service = self.make_service(client)
        result = await service.review_event("实验报告", preference, content, {"review_entry_id": 42})
        request = client.complete_json.call_args.kwargs
        self.assertIn(content, request["user"])
        self.assertIn(preference, request["user"])
        self.assertEqual(request["context"], {"stage": "review", "review_entry_id": 42})
        self.assertEqual(result, decision)
        client.complete_json.assert_awaited_once()

    async def test_context_error_is_not_replaced_with_truncated_review_or_rejection(self):
        client = Mock(complete_json=AsyncMock(side_effect=RuntimeError("context length exceeded")))
        service = self.make_service(client)
        with self.assertRaisesRegex(RuntimeError, "context length exceeded"):
            await service.review_event("长文", "保留实践", "全文内容" * 5000)
        client.complete_json.assert_awaited_once()

    async def test_short_and_missing_body_still_return_existing_contract(self):
        decision = {"passed": False, "score": 2, "reason": "信息不足", "category": "其他", "summary": "信息不足"}
        client = Mock(complete_json=AsyncMock(return_value=decision))
        service = self.make_service(client)
        for content in ("一条简短快讯", ""):
            with self.subTest(content=content):
                self.assertEqual(await service.review_event("标题", "要求具体依据", content), decision)
                self.assertIn(f"提供的正文：\n{content}\n", client.complete_json.call_args.kwargs["user"])
