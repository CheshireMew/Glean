from __future__ import annotations

import asyncio
import random
import re
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page

from .user_agents import get_random_user_agent


async def init_browser(scraper, headless: bool = True):
    from playwright.async_api import async_playwright

    scraper.playwright = await async_playwright().start()
    scraper.browser = await scraper.playwright.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-infobars",
        ],
    )
    scraper.page = await scraper.browser.new_page()
    await scraper.page.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        """
    )

    viewport = random.choice(
        [
            {"width": 1920, "height": 1080},
            {"width": 1366, "height": 768},
            {"width": 1536, "height": 864},
            {"width": 1440, "height": 900},
            {"width": 2560, "height": 1440},
        ]
    )
    await scraper.page.set_viewport_size(viewport)
    scraper.page.set_default_timeout(30000)
    scraper.page.set_default_navigation_timeout(30000)


async def close_browser(scraper):
    errors = []
    for resource in (scraper.page, scraper.browser):
        if resource:
            try:
                await resource.close()
            except Exception as exc:
                errors.append(exc)
    if scraper.playwright:
        try:
            await scraper.playwright.stop()
        except Exception as exc:
            errors.append(exc)
    scraper.page = None
    scraper.browser = None
    scraper.playwright = None
    if errors:
        raise RuntimeError("浏览器资源未能完整关闭") from errors[0]


async def fetch_page_with_delay(
    scraper,
    url: str,
    delay_range: tuple = (1, 3),
    max_retries: int = 3,
    return_response: bool = False,
    page: Optional["Page"] = None,
):
    target_page = page if page else scraper.page
    mean_delay = sum(delay_range) / 2
    std_delay = (delay_range[1] - delay_range[0]) / 4
    delay = max(delay_range[0], min(delay_range[1], random.gauss(mean_delay, std_delay)))
    await asyncio.sleep(delay)

    for attempt in range(max_retries):
        try:
            user_agent = get_random_user_agent()
            headers = {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
            }
            if "Chrome" in user_agent and "Edg" not in user_agent:
                match = re.search(r"Chrome/(\d+)", user_agent)
                chrome_version = match.group(1) if match else "131"
                headers["sec-ch-ua"] = f'"Chromium";v="{chrome_version}", "Google Chrome";v="{chrome_version}", "Not?A_Brand";v="99"'
                headers["sec-ch-ua-mobile"] = "?0"
                headers["sec-ch-ua-platform"] = '"Windows"' if "Windows" in user_agent else ('"macOS"' if "Mac" in user_agent else '"Linux"')

            await target_page.set_extra_http_headers(headers)
            response = await target_page.goto(url, wait_until="domcontentloaded")
            return response if return_response else target_page
        except Exception as exc:
            if attempt < max_retries - 1:
                wait_time = 2**attempt + random.uniform(0, 1)
                print(f"[反爬] 请求失败，{wait_time:.1f}秒后重试 (attempt {attempt + 1}/{max_retries}): {str(exc)[:50]}")
                await asyncio.sleep(wait_time)
            else:
                print(f"[反爬] 请求最终失败 ({max_retries}次重试后): {url}")
                raise
