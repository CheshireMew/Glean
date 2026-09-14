from __future__ import annotations

import asyncio
import html
import json
import re
import smtplib
import uuid
from email.message import EmailMessage

import httpx

from shared.content_contract import (
    DELIVERY_PART_STATUS_FAILED,
    DELIVERY_PART_STATUS_SENT,
    DELIVERY_PART_STATUS_UNKNOWN,
)

from ..core.exceptions import NotFoundError


def _plain_text(value: str) -> str:
    value = re.sub(
        r'<a\s+href="([^"]+)"[^>]*>(.*?)</a>',
        lambda match: f"{re.sub(r'<[^>]+>', '', match.group(2))} ({match.group(1)})",
        value,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


class PublicationChannelGateway:
    def __init__(self, publication_repository, telegram_gateway):
        self._publication_repository = publication_repository
        self._telegram_gateway = telegram_gateway

    def _channel(self, slug: str) -> dict:
        channel = self._publication_repository().get_channel_by_slug(slug)
        if not channel:
            raise NotFoundError("投递渠道不存在")
        if not channel.get("enabled"):
            raise ValueError("投递渠道已停用")
        return channel

    def channel_is_configured(self, slug: str) -> bool:
        try:
            channel = self._channel(slug)
        except (NotFoundError, ValueError):
            return False
        config = channel.get("config") or {}
        if channel["channel_type"] == "telegram":
            return self._telegram_gateway.has_bot_config() if slug == "telegram-default" and not config else bool(config.get("bot_token") and config.get("chat_id"))
        if channel["channel_type"] in {"webhook", "discord", "slack"}:
            return bool(config.get("url"))
        if channel["channel_type"] == "email":
            return bool(config.get("host") and config.get("from_address") and config.get("to_addresses"))
        return False

    @staticmethod
    def _split_plain_text(value: str, limit: int) -> list[str]:
        chunks = []
        remaining = value.strip()
        while remaining:
            if len(remaining) <= limit:
                chunks.append(remaining)
                break
            floor = max(1, int(limit * 0.6))
            split_at = max(remaining.rfind("\n", floor, limit + 1), remaining.rfind(" ", floor, limit + 1))
            split_at = split_at if split_at > 0 else limit
            chunks.append(remaining[:split_at].strip())
            remaining = remaining[split_at:].lstrip()
        return [chunk for chunk in chunks if chunk]

    def prepare_messages(self, channel_slug: str, messages: list[str]) -> list[str]:
        channel = self._channel(channel_slug)
        if channel["channel_type"] != "discord":
            return messages
        return [
            chunk
            for message in messages
            for chunk in self._split_plain_text(_plain_text(message), 2000)
        ]

    def message_limit(self, channel_slug: str) -> int:
        channel_type = self._channel(channel_slug)["channel_type"]
        return {
            "telegram": 4096,
            "discord": 2000,
            "slack": 40000,
            "webhook": 1_000_000,
            "email": 5_000_000,
        }.get(channel_type, 4096)

    async def send_message_result(self, channel_slug: str, text: str) -> dict:
        try:
            channel = self._channel(channel_slug)
            channel_type = channel["channel_type"]
            config = channel.get("config") or {}
            if channel_type == "telegram":
                if channel_slug == "telegram-default" and not config:
                    return await self._telegram_gateway.send_message_result(text)
                return await self._telegram_gateway.require_bot(config).send_message_result(text)
            if channel_type in {"webhook", "discord", "slack"}:
                return await self._send_webhook(channel_type, config, text)
            if channel_type == "email":
                return await self._send_email(config, text)
            return self._failed(f"不支持的投递渠道类型：{channel_type}")
        except (NotFoundError, ValueError, KeyError) as exc:
            return self._failed(str(exc))

    async def send_json_result(self, channel_slug: str, payload: dict) -> dict:
        try:
            channel = self._channel(channel_slug)
            if channel["channel_type"] != "webhook":
                return self._failed("结构化分析师订阅只支持 Webhook 渠道")
            config = channel.get("config") or {}
            url = str(config.get("url") or "").strip()
            if not url:
                return self._failed("Webhook URL 未配置")
            headers = {str(key): str(value) for key, value in (config.get("headers") or {}).items()}
            async with httpx.AsyncClient(timeout=float(config.get("timeout_seconds") or 15)) as client:
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code < 200 or response.status_code >= 300:
                    return self._failed(f"Webhook HTTP {response.status_code}: {response.text[:500]}")
                return {
                    "status": DELIVERY_PART_STATUS_SENT,
                    "error": None,
                    "remote_message_id": response.headers.get("x-request-id"),
                }
        except httpx.RequestError as exc:
            return self._unknown(f"Webhook 网络结果不确定：{exc}")
        except (NotFoundError, ValueError, KeyError) as exc:
            return self._failed(str(exc))

    async def test_channel(self, channel_id: int) -> dict:
        channel = self._publication_repository().get_channel(channel_id)
        if not channel:
            raise NotFoundError("投递渠道不存在")
        result = await self.send_message_result(
            channel["slug"],
            "🔔 <b>Glean 渠道测试</b>\n这是一条测试消息。",
        )
        return {"channel_id": channel_id, "channel_slug": channel["slug"], **result}

    async def _send_webhook(self, channel_type: str, config: dict, text: str) -> dict:
        url = str(config.get("url") or "").strip()
        if not url:
            return self._failed("Webhook URL 未配置")
        plain = _plain_text(text)
        if channel_type == "discord":
            if len(plain) > 2000:
                return self._failed("Discord 消息超过 2000 字符且尚未分段")
            payload = {"content": plain}
        elif channel_type == "slack":
            payload = {"text": plain}
        else:
            payload = {
                # Existing consumers rely on this stable Webhook event type.
                "event": "ainews.publication",
                "message_id": uuid.uuid4().hex,
                "text": plain,
                "html": text,
            }
        headers = {str(key): str(value) for key, value in (config.get("headers") or {}).items()}
        try:
            async with httpx.AsyncClient(timeout=float(config.get("timeout_seconds") or 15)) as client:
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code < 200 or response.status_code >= 300:
                    return self._failed(f"Webhook HTTP {response.status_code}: {response.text[:500]}")
                remote_id = response.headers.get("x-request-id")
                if not remote_id:
                    try:
                        body = response.json()
                        remote_id = str(body.get("id") or body.get("ts") or "") if isinstance(body, dict) else ""
                    except (ValueError, json.JSONDecodeError):
                        remote_id = ""
                return {"status": DELIVERY_PART_STATUS_SENT, "error": None, "remote_message_id": remote_id or None}
        except httpx.RequestError as exc:
            return self._unknown(f"Webhook 网络结果不确定：{exc}")

    async def _send_email(self, config: dict, text: str) -> dict:
        required = ["host", "from_address", "to_addresses"]
        missing = [key for key in required if not config.get(key)]
        if missing:
            return self._failed(f"邮件渠道缺少配置：{', '.join(missing)}")
        recipients = config["to_addresses"]
        if isinstance(recipients, str):
            recipients = [item.strip() for item in recipients.split(",") if item.strip()]
        if not recipients:
            return self._failed("邮件收件人为空")

        def send_sync() -> str | None:
            message = EmailMessage()
            message["Subject"] = str(config.get("subject") or "Glean 内容更新")
            message["From"] = str(config["from_address"])
            message["To"] = ", ".join(recipients)
            message.set_content(_plain_text(text))
            message.add_alternative(text.replace("\n", "<br>"), subtype="html")
            host = str(config["host"])
            port = int(config.get("port") or (465 if config.get("use_ssl") else 587))
            smtp_class = smtplib.SMTP_SSL if config.get("use_ssl") else smtplib.SMTP
            with smtp_class(host, port, timeout=float(config.get("timeout_seconds") or 20)) as smtp:
                if config.get("use_tls") and not config.get("use_ssl"):
                    smtp.starttls()
                if config.get("username"):
                    smtp.login(str(config["username"]), str(config.get("password") or ""))
                smtp.send_message(message)
            return message.get("Message-ID")

        try:
            remote_id = await asyncio.to_thread(send_sync)
            return {"status": DELIVERY_PART_STATUS_SENT, "error": None, "remote_message_id": remote_id}
        except (smtplib.SMTPAuthenticationError, smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused) as exc:
            return self._failed(f"邮件服务器拒绝发送：{exc}")
        except (OSError, smtplib.SMTPException) as exc:
            return self._unknown(f"邮件发送结果不确定：{exc}")

    @staticmethod
    def _failed(error: str) -> dict:
        return {"status": DELIVERY_PART_STATUS_FAILED, "error": error, "remote_message_id": None}

    @staticmethod
    def _unknown(error: str) -> dict:
        return {"status": DELIVERY_PART_STATUS_UNKNOWN, "error": error, "remote_message_id": None}
