from __future__ import annotations

import asyncio
import random
from typing import Optional, TYPE_CHECKING
from urllib.parse import urljoin
from urllib.parse import urlsplit
from ...core.config import settings
from ...core.outbound_http import safe_http_client, validate_url

if TYPE_CHECKING:
    from playwright.async_api import Page

from .source_access import source_access, source_host, SourceAccessError


async def init_browser(scraper, headless: bool = True):
    from playwright.async_api import async_playwright

    scraper._source_access_error = None
    scraper._source_redirects = {}
    scraper._source_requests = {}
    scraper._source_closing = False
    scraper._source_closing_pages = set()
    scraper._source_access = source_access
    scraper.playwright = await async_playwright().start()
    scraper.browser = await scraper.playwright.chromium.launch(headless=headless, chromium_sandbox=True)
    scraper._safe_http = safe_http_client(timeout=30) if settings.ENV == 'production' else None
    scraper.browser_context = await scraper.browser.new_context(
        viewport={"width": 1440, "height": 900}, locale="zh-CN", service_workers="block",
    )
    async def handle_route(route):
        request = route.request
        pending = None
        if (not is_prefetch(request) and request.resource_type in {"document", "xhr", "fetch"}
                and request_budget_url(scraper, request.url) == scraper.base_url):
            pending = scraper._source_requests.setdefault(request.frame.page, set())
            pending.add(asyncio.current_task())
        try:
            await pace_browser_request(scraper, route)
        finally:
            if pending is not None:
                pending.discard(asyncio.current_task())

    async def handle_response(response):
        await inspect_browser_response(scraper, response)

    await scraper.browser_context.route("**/*", handle_route)
    scraper.browser_context.on("response", handle_response)
    if settings.ENV == 'production':
        async def close_socket(websocket):
            await websocket.close()
        await scraper.browser_context.route_web_socket('**/*', close_socket)
    scraper.page = await scraper.browser_context.new_page()
    scraper.page.set_default_timeout(30000)
    scraper.page.set_default_navigation_timeout(60000)


def request_budget_url(scraper, url):
    site = source_host(scraper.base_url)
    host = source_host(url)
    return scraper.base_url if host == site or host.endswith("." + site) else url


def is_prefetch(request):
    headers = getattr(request, "headers", {})
    return ("prefetch" in headers.get("purpose", "").lower()
            or "prefetch" in headers.get("sec-purpose", "").lower()
            or headers.get("next-router-prefetch") == "1")


def request_is_closing(scraper, request):
    if getattr(scraper, "_source_closing", False):
        return True
    try:
        page = request.frame.page
        return page.is_closed() or page in getattr(scraper, "_source_closing_pages", set())
    except Exception:
        return False


async def abort_browser_request(scraper, route):
    try:
        await route.abort()
    except Exception:
        if not request_is_closing(scraper, route.request):
            raise


async def pace_browser_request(scraper, route):
    request = route.request
    essential_request = request.resource_type == "document" or request_budget_url(scraper, request.url) == scraper.base_url
    if (scraper._source_access_error or is_prefetch(request)
            or request.resource_type in {"image", "media", "font"}):
        await abort_browser_request(scraper, route)
        return
    try:
        budget_url = request_budget_url(scraper, request.url)
        if request.resource_type in {"document", "xhr", "fetch"}:
            await scraper._source_access.wait(budget_url)
        else:
            scraper._source_access.assert_allowed(budget_url)
        if scraper._source_access_error:
            await abort_browser_request(scraper, route)
        elif request.resource_type in {"document", "xhr", "fetch"} or settings.ENV == 'production':
            # Playwright routing does not re-intercept native HTTP redirects.
            # Fetch one hop at a time so every destination uses the same gate.
            url = request.url
            method = request.method
            headers_for_request = {k: v for k, v in (await request.all_headers()).items()
                                   if k.lower() not in {'host', 'content-length'}} if settings.ENV == 'production' else {}
            body = request.post_data_buffer if settings.ENV == 'production' else None
            for hop in range(6):
                response = (await scraper._safe_http.request(method, url, headers=headers_for_request, content=body)
                            if settings.ENV == 'production' else
                            await route.fetch(url=url, method=method, max_redirects=0, max_retries=0, timeout=30000))
                try:
                    headers = response.headers
                    status = response.status_code if settings.ENV == 'production' else response.status
                    text = response.text if settings.ENV == 'production' else await response.text()
                    scraper._source_access.inspect(request_budget_url(scraper, url), status, headers, text)
                    if status in (301, 302, 303, 307, 308) and headers.get("location"):
                        if hop == 5:
                            raise SourceAccessError("页面重定向次数过多，已停止")
                        destination = urljoin(url, headers["location"])
                        validate_url(destination)
                        if urlsplit(url).netloc != urlsplit(destination).netloc:
                            headers_for_request = {k: v for k, v in headers_for_request.items()
                                                   if k.lower() not in {'cookie', 'authorization'}}
                        url = destination
                        scraper._source_access.assert_allowed(request_budget_url(scraper, url))
                        if request.resource_type == "document" and request.frame == request.frame.page.main_frame:
                            # Re-navigate explicitly to preserve the final page URL
                            # and relative links instead of replaying a hidden redirect.
                            scraper._source_redirects[request.frame.page] = url
                            await route.fulfill(status=200, content_type="text/html", body="")
                            return
                        if status == 303 or (status in (301, 302) and method == "POST"):
                            method = "GET"
                            body = None
                        await scraper._source_access.wait(request_budget_url(scraper, url))
                        continue
                    if settings.ENV == 'production':
                        await route.fulfill(status=status, headers=dict(headers), body=response.content)
                    else:
                        await route.fulfill(response=response)
                    return
                finally:
                    if settings.ENV == 'production':
                        await response.aclose()
                    else:
                        await response.dispose()
        else:
            await route.continue_()
    except SourceAccessError as exc:
        if essential_request:
            scraper._source_access_error = exc
        await abort_browser_request(scraper, route)
    except Exception as exc:
        if request_is_closing(scraper, request):
            return
        # A routing error must resolve the paused browser request and fail closed.
        error = scraper._source_access.defer(
            request_budget_url(scraper, request.url), f"浏览器请求未完成（{type(exc).__name__}）", minimum=600)
        if essential_request:
            scraper._source_access_error = error
        await abort_browser_request(scraper, route)


async def inspect_browser_response(scraper, response):
    if (scraper._source_access_error or request_is_closing(scraper, response.request)
            or response.request.resource_type not in {"document", "xhr", "fetch"}):
        return
    try:
        budget_url = request_budget_url(scraper, response.url)
        # Unrelated analytics failures must not stop the article collector.
        if budget_url != scraper.base_url and response.request.resource_type != "document":
            return
        scraper._source_access.inspect(budget_url, response.status, response.headers)
    except SourceAccessError as exc:
        scraper._source_access_error = exc


async def cancel_page_requests(scraper, page):
    getattr(scraper, "_source_closing_pages", set()).add(page)
    tasks = list(getattr(scraper, "_source_requests", {}).get(page, set()))
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    getattr(scraper, "_source_requests", {}).pop(page, None)


async def close_browser(scraper):
    scraper._source_closing = True
    for page in list(getattr(scraper, "_source_requests", {})):
        await cancel_page_requests(scraper, page)
    errors = []
    for resource in (getattr(scraper, '_safe_http', None), getattr(scraper, "browser_context", None), scraper.browser):
        if resource:
            try:
                if hasattr(resource, 'aclose'):
                    await resource.aclose()
                else:
                    await resource.close()
            except Exception as exc:
                errors.append(exc)
    if scraper.playwright:
        try:
            await scraper.playwright.stop()
        except Exception as exc:
            errors.append(exc)
    scraper.page = None
    scraper.browser_context = None
    scraper.browser = None
    scraper.playwright = None
    if errors:
        raise RuntimeError("浏览器资源未能完整关闭") from errors[0]


async def wait_for_source_requests(scraper, page):
    # Existing parsers assume the list API has loaded. Pacing those API calls
    # must not turn a slow response into an apparently empty article list.
    if not hasattr(scraper, "_source_requests"):
        return
    deadline = asyncio.get_running_loop().time() + 60
    while True:
        await asyncio.sleep(0.2)
        if scraper._source_access_error:
            raise scraper._source_access_error
        if not scraper._source_requests.get(page):
            return
        if asyncio.get_running_loop().time() >= deadline:
            raise scraper._source_access.defer(scraper.base_url, "页面接口等待超时，暂停后再试", minimum=600)


async def fetch_page_with_delay(
    scraper,
    url: str,
    delay_range: tuple = (1, 3),
    max_retries: int = 3,
    return_response: bool = False,
    page: Optional["Page"] = None,
):
    from playwright.async_api import Error as BrowserError

    validate_url(url)
    target_page = page if page else scraper.page
    attempts = max(1, min(max_retries, 2))
    for attempt in range(attempts):
        if scraper._source_access_error:
            raise scraper._source_access_error
        scraper._source_access.assert_allowed(request_budget_url(scraper, url))
        try:
            # Context routing paces documents and page-generated API requests,
            # including redirects and detail pages, before they reach the site.
            for hop in range(6):
                response = await target_page.goto(url, wait_until="domcontentloaded", timeout=60000)
                destination = getattr(scraper, "_source_redirects", {}).pop(target_page, None)
                if not destination:
                    break
                if hop == 5:
                    raise SourceAccessError("页面重定向次数过多，已停止")
                url = destination
            if scraper._source_access_error:
                raise scraper._source_access_error
            await wait_for_source_requests(scraper, target_page)
            if response is None:
                raise SourceAccessError("页面没有返回有效响应")
            budget_url = request_budget_url(scraper, response.url)
            scraper._source_access.inspect(budget_url, response.status, response.headers, await target_page.content())
            if response.status >= 500:
                if attempt == attempts - 1:
                    raise scraper._source_access.defer(budget_url, f"HTTP {response.status}，连续服务异常", minimum=600)
                await asyncio.sleep(30 + random.uniform(0, 5))
                continue
            if response.status >= 400:
                raise SourceAccessError(f"HTTP {response.status}，停止采集该页面")
            return response if return_response else target_page
        except SourceAccessError as exc:
            scraper._source_access_error = exc
            raise
        except BrowserError:
            if scraper._source_access_error:
                raise scraper._source_access_error
            if attempt == attempts - 1:
                error = scraper._source_access.defer(request_budget_url(scraper, url), "连续页面请求错误或超时", minimum=600)
                scraper._source_access_error = error
                raise error
            await asyncio.sleep(30 + random.uniform(0, 5))
