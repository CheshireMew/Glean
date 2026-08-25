from __future__ import annotations

import asyncio
import random
from abc import ABC, abstractmethod
from email.utils import parsedate_to_datetime
from typing import Any, Dict

import httpx

from .browser_runtime import close_browser, fetch_page_with_delay, init_browser
from .user_agents import get_random_user_agent


class SourceTransport(ABC):
    kind: str

    @abstractmethod
    async def start(self, owner) -> None:
        raise NotImplementedError

    @abstractmethod
    async def close(self, owner) -> None:
        raise NotImplementedError


class BrowserSourceTransport(SourceTransport):
    kind = "browser"

    async def start(self, owner) -> None:
        await init_browser(owner)

    async def close(self, owner) -> None:
        await close_browser(owner)
        owner.page = None
        owner.browser = None
        owner.playwright = None

    async def fetch_page(self, owner, url: str, **kwargs):
        return await fetch_page_with_delay(owner, url, **kwargs)


class HttpSourceTransport(SourceTransport):
    kind = "http"

    def __init__(self, timeout_seconds: float = 30.0):
        self.timeout_seconds = timeout_seconds
        self.client: httpx.AsyncClient | None = None

    async def start(self, owner) -> None:
        self.client = httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": get_random_user_agent(),
                "Accept": "application/json, application/rss+xml, application/atom+xml, text/xml, text/html;q=0.9, */*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )

    async def close(self, owner) -> None:
        if self.client:
            await self.client.aclose()
            self.client = None

    @staticmethod
    def _retry_after_seconds(response: httpx.Response, attempt: int) -> float:
        value = response.headers.get("Retry-After", "").strip()
        if value:
            try:
                return min(max(float(value), 0.0), 120.0)
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(value)
                    return min(max((retry_at.timestamp() - __import__("time").time()), 0.0), 120.0)
                except Exception:
                    pass
        return min(2 ** attempt + random.uniform(0, 1), 30.0)

    async def fetch(self, url: str, delay_range: tuple[float, float] = (0.3, 1.0), max_retries: int = 3) -> httpx.Response:
        if not self.client:
            raise RuntimeError("HTTP transport has not been started")
        await asyncio.sleep(random.uniform(*delay_range))
        for attempt in range(max_retries):
            try:
                response = await self.client.get(url)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt == max_retries - 1:
                        response.raise_for_status()
                    await asyncio.sleep(self._retry_after_seconds(response, attempt))
                    continue
                response.raise_for_status()
                return response
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(min(2 ** attempt + random.uniform(0, 1), 30.0))
        raise RuntimeError(f"HTTP source failed without a response: {url}")

    async def fetch_text(self, url: str, **kwargs) -> str:
        response = await self.fetch(url, **kwargs)
        return response.text

    async def fetch_json(self, url: str, **kwargs) -> Dict[str, Any] | list:
        response = await self.fetch(url, **kwargs)
        return response.json()


def create_source_transport(kind: str) -> SourceTransport:
    if kind == "browser":
        return BrowserSourceTransport()
    if kind in {"http", "api", "rss"}:
        return HttpSourceTransport()
    raise ValueError(f"Unsupported source transport: {kind}")
