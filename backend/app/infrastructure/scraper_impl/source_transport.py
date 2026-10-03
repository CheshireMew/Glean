from __future__ import annotations

import asyncio
import random
from abc import ABC, abstractmethod
from typing import Any, Dict
from urllib.parse import urljoin

import httpx

from .browser_runtime import close_browser, fetch_page_with_delay, init_browser
from .source_access import source_access, SourceAccessError


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

    def __init__(self, timeout_seconds: float = 30.0, access=None):
        self.timeout_seconds = timeout_seconds
        self.client: httpx.AsyncClient | None = None
        self.access = access or source_access

    async def start(self, owner) -> None:
        self.client = httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=False,
            headers={
                "User-Agent": "Glean/0.1 (+https://github.com/CheshireMew/Glean)",
                "Accept": "application/json, application/rss+xml, application/atom+xml, text/xml, text/html;q=0.9, */*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )

    async def close(self, owner) -> None:
        if self.client:
            await self.client.aclose()
            self.client = None

    async def fetch(self, url: str, delay_range: tuple[float, float] = (0.3, 1.0), max_retries: int = 3,
                    *, method: str = "GET", json_body: dict | None = None) -> httpx.Response:
        if not self.client:
            raise RuntimeError("HTTP transport has not been started")
        attempts = max(1, min(max_retries, 2))
        for attempt in range(attempts):
            current_url, current_method, current_body = url, method.upper(), json_body
            try:
                for redirect in range(6):
                    await self.access.wait(current_url)
                    response = await self.client.request(current_method, current_url, json=current_body)
                    self.access.inspect(current_url, response.status_code, response.headers, response.text[:65536])
                    if response.status_code in (301, 302, 303, 307, 308) and response.headers.get("location"):
                        if redirect == 5:
                            raise SourceAccessError("采集地址重定向次数过多，已停止")
                        current_url = urljoin(current_url, response.headers["location"])
                        if response.status_code == 303 or (response.status_code in (301, 302) and current_method == "POST"):
                            current_method, current_body = "GET", None
                        continue
                    break
                if response.status_code >= 500:
                    if attempt == attempts - 1:
                        raise self.access.defer(current_url, f"HTTP {response.status_code}，连续服务异常", minimum=600)
                    await asyncio.sleep(30 + random.uniform(0, 5))
                    continue
                response.raise_for_status()
                return response
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt == attempts - 1:
                    raise self.access.defer(current_url, "连续网络错误或超时", minimum=600)
                await asyncio.sleep(30 + random.uniform(0, 5))
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
