import httpx
import logging

from shared.content_contract import (
    DELIVERY_PART_STATUS_FAILED,
    DELIVERY_PART_STATUS_SENT,
    DELIVERY_PART_STATUS_UNKNOWN,
)

logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    async def send_message(self, text: str, parse_mode: str = 'HTML') -> bool:
        """
        Send a message to the configured telegram chat.
        Returns True if successful, False otherwise.
        """
        result = await self.send_message_result(text, parse_mode)
        return result["status"] == DELIVERY_PART_STATUS_SENT

    async def send_message_result(self, text: str, parse_mode: str = "HTML") -> dict:
        if not self.token or not self.chat_id:
            return {"status": DELIVERY_PART_STATUS_FAILED, "error": "Telegram Token 或 Chat ID 缺失", "remote_message_id": None}

        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, timeout=10.0)
                if response.status_code != 200:
                    error = f"Telegram HTTP {response.status_code}: {response.text[:500]}"
                    logger.error(error)
                    return {"status": DELIVERY_PART_STATUS_FAILED, "error": error, "remote_message_id": None}
                payload_result = response.json()
                if not payload_result.get("ok"):
                    error = str(payload_result.get("description") or "Telegram 返回未知错误")
                    return {"status": DELIVERY_PART_STATUS_FAILED, "error": error, "remote_message_id": None}
                message_id = (payload_result.get("result") or {}).get("message_id")
                logger.info("Telegram push succeeded chat_id=%s message_id=%s", self.chat_id, message_id)
                return {"status": DELIVERY_PART_STATUS_SENT, "error": None, "remote_message_id": str(message_id) if message_id is not None else None}
        except httpx.RequestError as exc:
            error = f"Telegram 网络结果不确定: {exc}"
            logger.error(error)
            return {"status": DELIVERY_PART_STATUS_UNKNOWN, "error": error, "remote_message_id": None}
        except Exception as exc:
            error = f"Telegram 响应解析失败: {exc}"
            logger.exception(error)
            return {"status": DELIVERY_PART_STATUS_UNKNOWN, "error": error, "remote_message_id": None}

    async def test_connection(self) -> dict:
        """
        Test the bot token validation (getMe).
        """
        if not self.token:
            return {"ok": False, "error": "Token missing"}
            
        url = f"{self.base_url}/getMe"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=10.0)
                return response.json()
        except Exception as e:
             return {"ok": False, "error": str(e)}
