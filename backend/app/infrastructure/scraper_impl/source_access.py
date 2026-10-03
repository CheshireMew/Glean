"""Shared, persistent request pacing and backoff for public sources."""
from __future__ import annotations

import asyncio
from contextlib import closing
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import math
import random
import re
import time
from urllib.parse import urlparse

from ..database import database


class SourceAccessError(RuntimeError):
    pass


class SourceCoolingDown(SourceAccessError):
    def __init__(self, host, until, reason):
        self.host, self.until, self.reason = host, until, reason
        try:
            resume = datetime.fromtimestamp(until, timezone.utc).astimezone().strftime("%m-%d %H:%M:%S")
        except (ValueError, OverflowError, OSError):
            resume = "网站指定的等待期结束"
        super().__init__(f"{host} 暂停采集至 {resume}：{reason}")


def source_host(url):
    host = (urlparse(str(url)).hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError("采集地址缺少主机名")
    # Group common first-party content hosts without collapsing arbitrary
    # multi-tenant domains such as different *.github.io sites.
    for prefix in ("www.", "api.", "rss.", "m."):
        if host.startswith(prefix):
            return host[len(prefix):]
    return host


def retry_after_seconds(value, now=None):
    """Honor the full server delay; never cap it to an earlier retry."""
    if not value:
        return None
    now = time.time() if now is None else now
    try:
        seconds = float(value)
    except (ValueError, TypeError):
        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            seconds = parsed.timestamp() - now
        except (ValueError, TypeError, OverflowError):
            return None
    return max(seconds, 0) if math.isfinite(seconds) else None


def is_challenge_page(text):
    # Match challenge page titles, not news articles discussing captchas.
    title = re.search(r"<title[^>]*>\s*(.*?)\s*</title>", (text or "")[:65536], re.I | re.S)
    if not title:
        return False
    title = re.sub(r"\s+", " ", title.group(1)).strip().lower()
    return title in {
        "just a moment...", "attention required! | cloudflare", "verify you are human",
        "checking your browser", "security verification", "访问验证", "安全验证",
        "人机验证", "访问过于频繁", "访问受限", "access denied", "too many requests",
    }


class SourceAccess:
    def __init__(self, db=database, clock=time.time, spacing=lambda: random.uniform(5, 8)):
        self.db, self.clock, self.spacing = db, clock, spacing

    def _read(self, conn, host):
        row = conn.execute("SELECT value FROM system_config WHERE key=?", (f"scraping.access.{host}",)).fetchone()
        return json.loads(row[0]) if row else {}

    @staticmethod
    def _write(conn, host, state):
        conn.execute(
            "INSERT INTO system_config(key,value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP",
            (f"scraping.access.{host}", json.dumps(state)),
        )

    def cooldown(self, url):
        host = source_host(url)
        with closing(self.db.connect()) as conn:
            state = self._read(conn, host)
        until = state.get("cooldown_until", 0)
        return SourceCoolingDown(host, until, state.get("reason", "网站要求稍后再试")) if until > self.clock() else None

    def assert_allowed(self, url):
        error = self.cooldown(url)
        if error:
            raise error

    def for_definition(self, definition):
        if definition.name.startswith("wechat__"):
            return None
        scraper = definition.build_scraper()
        url = getattr(scraper, "feed_url", None) or getattr(scraper, "api_url", None) or scraper.base_url
        return self.cooldown(url) or self.cooldown(scraper.base_url)

    def reserve(self, url):
        host = source_host(url)
        with closing(self.db.connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                state = self._read(conn, host)
                now = self.clock()
                if state.get("cooldown_until", 0) > now:
                    raise SourceCoolingDown(host, state["cooldown_until"], state.get("reason", "网站限流"))
                wait = max(state.get("next_request_at", 0) - now, 0)
                if not wait:
                    state["next_request_at"] = now + self.spacing()
                    self._write(conn, host, state)
                conn.commit()
                return wait
            except BaseException:
                conn.rollback()
                raise

    async def wait(self, url):
        while True:
            wait = self.reserve(url)
            if not wait:
                return
            await asyncio.sleep(min(wait, 1))

    def defer(self, url, reason, retry_after=None, minimum=1800):
        host = source_host(url)
        with closing(self.db.connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                state = self._read(conn, host)
                now = self.clock()
                previous = state.get("blocked_count", 0) if now - state.get("last_blocked_at", 0) < 86400 else 0
                count = min(previous + 1, 7)
                delay = max(min(minimum * 2 ** (count - 1), 86400), retry_after_seconds(retry_after, now) or 0)
                state.update(cooldown_until=max(state.get("cooldown_until", 0), now + delay),
                             reason=reason, blocked_count=count, last_blocked_at=now)
                self._write(conn, host, state)
                conn.commit()
                return SourceCoolingDown(host, state["cooldown_until"], reason)
            except BaseException:
                conn.rollback()
                raise

    def inspect(self, url, status, headers, text=""):
        headers = {key.lower(): value for key, value in headers.items()}
        reason = None
        if status in (403, 429):
            reason = f"HTTP {status}，网站拒绝访问或要求降低频率"
        elif headers.get("cf-mitigated", "").lower() == "challenge" or is_challenge_page(text):
            reason = "网站要求人机验证"
        elif (status >= 500 or 300 <= status < 400) and headers.get("retry-after"):
            reason = f"HTTP {status}，网站要求稍后重试"
        if reason:
            raise self.defer(url, reason, headers.get("retry-after"))


source_access = SourceAccess()
