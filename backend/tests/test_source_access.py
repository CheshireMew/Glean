from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from backend.app.infrastructure.scraper_impl import browser_runtime
from backend.app.infrastructure.scraper_impl.base import BaseScraper
from backend.app.infrastructure.scraper_impl.source_access import (
    SourceAccess, SourceCoolingDown, is_challenge_page, retry_after_seconds,
)
from backend.app.infrastructure.scraper_impl.source_transport import HttpSourceTransport
from backend.app.infrastructure.sqlite.db_sqlite import Database


class SourceAccessTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=r"D:\Tools")
        self.db = Database(str(Path(self.folder.name) / "pacing.db"))
        self.db.init_db()
        self.now = 1800000000.0
        self.guard = SourceAccess(self.db, clock=lambda: self.now, spacing=lambda: 5)

    async def asyncTearDown(self):
        self.folder.cleanup()

    def test_pacing_is_atomic_shared_between_instances_and_independent_by_site(self):
        other = SourceAccess(self.db, clock=lambda: self.now, spacing=lambda: 5)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda guard: guard.reserve("https://example.test/feed"), [self.guard, other]))
        self.assertEqual(sorted(results), [0, 5])
        self.assertEqual(other.reserve("https://www.example.test/article"), 5)
        self.assertEqual(other.reserve("https://api.example.test/list"), 5)
        self.assertEqual(other.reserve("https://different.test/feed"), 0)
        self.now += 5
        self.assertEqual(other.reserve("https://example.test/feed"), 0)

    def test_long_retry_after_survives_restart_and_repeated_blocks_extend_cooldown(self):
        first = self.guard.defer("https://example.test/feed", "HTTP 429", "7200")
        self.assertEqual(first.until, self.now + 7200)
        reopened = SourceAccess(Database(self.db.db_path), clock=lambda: self.now)
        with self.assertRaises(SourceCoolingDown):
            reopened.reserve("https://example.test/article")
        self.now += 7200
        second = reopened.defer("https://example.test/article", "HTTP 403")
        self.assertEqual(second.until, self.now + 3600)
        self.assertEqual(retry_after_seconds(format_datetime(datetime.fromtimestamp(self.now + 86400, timezone.utc)), self.now), 86400)
        for raw in ("bogus", "nan", "inf"):
            self.assertIsNone(retry_after_seconds(raw, self.now))

    async def test_cancel_while_waiting_does_not_consume_a_future_slot(self):
        self.guard.reserve("https://example.test/feed")
        task = asyncio.create_task(self.guard.wait("https://example.test/feed"))
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.now += 5
        self.assertEqual(self.guard.reserve("https://example.test/feed"), 0)

    def http(self, handler):
        self.guard.spacing = lambda: 0
        transport = HttpSourceTransport(access=self.guard)
        transport.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return transport

    async def test_429_is_one_request_and_manual_retry_makes_no_request(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(429, headers={"Retry-After": "86400"})
        transport = self.http(handler)
        try:
            for _ in range(2):
                with self.assertRaises(SourceCoolingDown) as caught:
                    await transport.fetch("https://example.test/feed")
                self.assertEqual(caught.exception.until, self.now + 86400)
            self.assertEqual(len(calls), 1)
        finally:
            await transport.close(None)

    async def test_403_and_html_challenge_stop_without_retries(self):
        for index, response in enumerate((httpx.Response(403), httpx.Response(200, text="<html><title>Just a moment...</title></html>"))):
            calls = []
            transport = self.http(lambda request: (calls.append(request), response)[1])
            try:
                with self.assertRaises(SourceCoolingDown):
                    await transport.fetch(f"https://blocked{index}.test/feed")
                self.assertEqual(len(calls), 1)
            finally:
                await transport.close(None)
        self.assertFalse(is_challenge_page("<title>AI 研究：人机验证的演进</title><p>验证码 captcha Cloudflare</p>"))

    async def test_503_retry_after_waits_without_retrying_in_task(self):
        calls = []
        transport = self.http(lambda request: (calls.append(request), httpx.Response(503, headers={"Retry-After": "10800"}))[1])
        try:
            with self.assertRaises(SourceCoolingDown) as caught:
                await transport.fetch("https://example.test/feed")
            self.assertEqual(caught.exception.until, self.now + 10800)
            self.assertEqual(len(calls), 1)
        finally:
            await transport.close(None)

    async def test_transient_failures_retry_once_then_cool_down(self):
        calls = []
        def handler(request):
            calls.append(request)
            raise httpx.ReadTimeout("slow", request=request)
        transport = self.http(handler)
        try:
            with patch("backend.app.infrastructure.scraper_impl.source_transport.asyncio.sleep", new=AsyncMock()) as sleep:
                with self.assertRaises(SourceCoolingDown):
                    await transport.fetch("https://example.test/feed")
                self.assertGreaterEqual(sleep.call_args.args[0], 30)
            self.assertEqual(len(calls), 2)
        finally:
            await transport.close(None)

    async def test_redirect_cannot_bypass_destination_cooldown(self):
        self.guard.defer("https://blocked.test/", "HTTP 429")
        calls = []
        transport = self.http(lambda request: (calls.append(request), httpx.Response(302, headers={"Location": "https://blocked.test/"}))[1])
        try:
            with self.assertRaises(SourceCoolingDown):
                await transport.fetch("https://example.test/feed")
            self.assertEqual(len(calls), 1)
        finally:
            await transport.close(None)

    def browser_owner(self):
        return SimpleNamespace(base_url="https://www.example.test/list", _source_access=self.guard, _source_access_error=None)

    async def test_browser_api_limit_blocks_further_pages_and_assets(self):
        owner = self.browser_owner()
        response = SimpleNamespace(url="https://api.example.test/articles", status=429, headers={"retry-after": "3600"},
                                   request=SimpleNamespace(resource_type="xhr"))
        await browser_runtime.inspect_browser_response(owner, response)
        self.assertIsInstance(owner._source_access_error, SourceCoolingDown)
        for kind in ("document", "xhr", "image"):
            route = SimpleNamespace(request=SimpleNamespace(resource_type=kind, url="https://www.example.test/next"), abort=AsyncMock(), continue_=AsyncMock())
            await browser_runtime.pace_browser_request(owner, route)
            route.abort.assert_awaited_once()
            route.continue_.assert_not_called()

    async def test_browser_unrelated_403_is_not_a_site_block_and_media_are_skipped(self):
        owner = self.browser_owner()
        response = SimpleNamespace(url="https://analytics.test/event", status=403, headers={}, request=SimpleNamespace(resource_type="fetch"))
        await browser_runtime.inspect_browser_response(owner, response)
        self.assertIsNone(owner._source_access_error)
        self.guard.spacing = lambda: 0
        api_response = SimpleNamespace(status=403, headers={}, dispose=AsyncMock())
        analytics = SimpleNamespace(request=SimpleNamespace(resource_type="fetch", url="https://analytics.test/event", method="GET"),
                                    fetch=AsyncMock(return_value=api_response), abort=AsyncMock())
        await browser_runtime.pace_browser_request(owner, analytics)
        analytics.abort.assert_awaited_once()
        self.assertIsNone(owner._source_access_error)
        self.assertIsNotNone(self.guard.cooldown("https://analytics.test/event"))
        route = SimpleNamespace(request=SimpleNamespace(resource_type="image", url="https://example.test/photo.jpg"), abort=AsyncMock(), continue_=AsyncMock())
        await browser_runtime.pace_browser_request(owner, route)
        route.abort.assert_awaited_once()
        route.continue_.assert_not_called()

    async def test_browser_200_challenge_is_not_returned_as_article_content(self):
        owner = self.browser_owner()
        response = SimpleNamespace(status=200, url=owner.base_url, headers={})
        owner.page = SimpleNamespace(goto=AsyncMock(return_value=response), content=AsyncMock(return_value="<title>安全验证</title>"))
        with self.assertRaises(SourceCoolingDown):
            await browser_runtime.fetch_page_with_delay(owner, owner.base_url)
        owner.page.goto.assert_awaited_once()

    async def test_swallowed_browser_block_still_fails_collection(self):
        error = self.guard.defer("https://example.test/", "人机验证")
        class Scraper(BaseScraper):
            async def scrape_important_news(inner):
                inner._source_access_error = error
                return []
        scraper = Scraper("test", "https://example.test/")
        scraper.transport = SimpleNamespace(start=AsyncMock(), close=AsyncMock())
        with self.assertRaises(SourceCoolingDown):
            await scraper.run()
        scraper.transport.close.assert_awaited_once()

    async def test_real_browser_routes_api_requests_assets_and_redirects(self):
        hits = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(inner):
                hits.append(inner.path)
                if inner.path == "/redirect":
                    inner.send_response(302)
                    inner.send_header("Location", f"http://localhost:{server.server_port}/landing")
                    inner.end_headers()
                    return
                if inner.path == "/slow":
                    time.sleep(0.6)
                inner.send_response(429 if inner.path == "/api" else 200)
                inner.send_header("Content-Type", "text/html")
                if inner.path == "/api":
                    inner.send_header("Retry-After", "7200")
                inner.end_headers()
                if inner.path == "/list":
                    inner.wfile.write(b'<title>Articles</title><img src="/image.png"><script>fetch("/api").then(() => fetch("/after"))</script>')
                elif inner.path == "/ready":
                    inner.wfile.write(b'<title>Articles</title><body><script>fetch("/slow").then(r => r.text()).then(() => document.body.dataset.loaded = "yes")</script>')
                elif inner.path == "/prefetch":
                    inner.wfile.write(b'<title>Articles</title><script>for(let i=0;i<20;i++) fetch("/prefetched?i="+i,{headers:{"Next-Router-Prefetch":"1"}}).catch(()=>{})</script>')
                else:
                    inner.wfile.write(b"ok")

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.guard.spacing = lambda: 0
        owner = SimpleNamespace(base_url=f"http://127.0.0.1:{server.server_port}/list", browser=None, page=None, playwright=None)
        try:
            with patch.object(browser_runtime, "source_access", self.guard):
                await browser_runtime.init_browser(owner)
            page = await browser_runtime.fetch_page_with_delay(owner, owner.base_url.replace('/list', '/redirect'))
            self.assertEqual(page.url, f"http://localhost:{server.server_port}/landing")
            self.assertEqual(hits.count("/landing"), 1)
            page = await browser_runtime.fetch_page_with_delay(owner, owner.base_url.replace('/list', '/ready'))
            self.assertEqual(await page.locator('body').get_attribute('data-loaded'), "yes")
            await browser_runtime.fetch_page_with_delay(owner, owner.base_url.replace('/list', '/prefetch'))
            self.assertFalse(any(path.startswith('/prefetched') for path in hits))
            # Close while a content request is still waiting for its response.
            await owner.page.goto(owner.base_url.replace('/list', '/ready'), wait_until='domcontentloaded')
            for _ in range(20):
                if owner._source_requests.get(owner.page):
                    break
                await asyncio.sleep(0.01)
            self.assertTrue(owner._source_requests.get(owner.page))
            await browser_runtime.close_browser(owner)
            self.assertIsNone(owner._source_access_error)
            self.assertIsNone(self.guard.cooldown(owner.base_url))
            with patch.object(browser_runtime, "source_access", self.guard):
                await browser_runtime.init_browser(owner)
            hits.clear()
            self.guard.defer(f"http://localhost:{server.server_port}/landing", "HTTP 429")
            with self.assertRaises(SourceCoolingDown):
                await browser_runtime.fetch_page_with_delay(owner, owner.base_url.replace('/list', '/redirect'))
            self.assertNotIn("/landing", hits)
            owner._source_access_error = None
            try:
                await browser_runtime.fetch_page_with_delay(owner, owner.base_url)
            except SourceCoolingDown:
                pass
            for _ in range(50):
                if owner._source_access_error:
                    break
                await asyncio.sleep(0.02)
            await asyncio.sleep(0.1)
            self.assertIsInstance(owner._source_access_error, SourceCoolingDown)
            self.assertEqual(hits.count("/api"), 1)
            self.assertNotIn("/after", hits)
            self.assertNotIn("/image.png", hits)
        finally:
            await browser_runtime.close_browser(owner)
            server.shutdown()
            server.server_close()
            thread.join()
