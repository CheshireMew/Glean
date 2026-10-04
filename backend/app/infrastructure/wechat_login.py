"""Short-lived browser login. Browser access stays on its own Windows thread."""
from __future__ import annotations

import base64
import threading
import time
from urllib.parse import parse_qs, urlparse
from uuid import uuid4


class WechatBrowserLogin:
    def __init__(self):
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._state = {'state': 'idle', 'message': ''}

    def snapshot(self):
        with self._lock:
            return dict(self._state)

    def _update(self, **values):
        with self._lock:
            self._state.update(values)

    def start(self, on_login):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return dict(self._state)
            self._stop = threading.Event()
            self._state = {'state': 'starting', 'message': '正在加载微信登录二维码',
                           'login_id': uuid4().hex, 'qr_image': None}
            self._thread = threading.Thread(target=self._run, args=(on_login,), daemon=True,
                                            name='wechat-login')
            self._thread.start()
            return dict(self._state)

    def close(self):
        self._stop.set()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=35)
        if thread and thread.is_alive():
            return False
        self._update(state='idle', qr_image=None, message='登录已取消')
        return True

    def _run(self, on_login):
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright

        try:
            with sync_playwright() as playwright:
                try:
                    browser = playwright.chromium.launch(headless=True, chromium_sandbox=True)
                except PlaywrightError:
                    # Windows installations commonly already have Edge.
                    browser = playwright.chromium.launch(headless=True, channel='msedge', chromium_sandbox=True)
                try:
                    context = browser.new_context(locale='zh-CN', viewport={'width': 1100, 'height': 850})
                    page = context.new_page()
                    page.set_default_timeout(3000)
                    page.goto('https://mp.weixin.qq.com/', wait_until='domcontentloaded', timeout=30000)
                    qr = page.locator('.login__type__container__scan__qrcode').first
                    deadline = time.monotonic() + 300
                    image_at = 0
                    while not self._stop.is_set() and time.monotonic() < deadline:
                        parsed = urlparse(page.url)
                        token = parse_qs(parsed.query).get('token', [''])[0]
                        if parsed.hostname == 'mp.weixin.qq.com' and parsed.path == '/cgi-bin/home' and token:
                            cookies = context.cookies('https://mp.weixin.qq.com/')
                            if not self._stop.is_set():
                                on_login({'token': token, 'cookies': cookies,
                                          'session_id': uuid4().hex, 'saved_at': time.time()})
                                self._update(state='success', qr_image=None, message='微信公众平台已登录')
                            return
                        if page.get_by_text('没有可登录账号', exact=False).count():
                            self._update(state='error', qr_image=None,
                                         message='这个微信号没有可登录的公众号，请先注册或绑定公众号')
                            return
                        if not qr.is_visible():
                            switch = page.get_by_text('扫码登录', exact=True)
                            if switch.count() and switch.first.is_visible():
                                switch.first.click()
                        if qr.is_visible() and qr.evaluate('(img) => img.complete && img.naturalWidth > 0'):
                            if time.monotonic() - image_at > 10:
                                image = base64.b64encode(qr.screenshot(timeout=3000)).decode('ascii')
                                self._update(state='waiting', qr_image='data:image/png;base64,' + image,
                                             message='请使用管理公众号的微信扫码，并在手机上确认登录')
                                image_at = time.monotonic()
                        elif self.snapshot().get('qr_image'):
                            self._update(state='scanned', message='请在手机上选择公众号并确认登录')
                        page.wait_for_timeout(1000)
                    self._update(state='expired', qr_image=None, message='二维码已过期，请重新获取')
                finally:
                    browser.close()
        except Exception:  # noqa: BLE001 - thread boundary must always publish a terminal status
            # Playwright errors can contain URLs with login tokens. Do not expose them.
            self._update(state='error', qr_image=None,
                         message='微信登录页面加载失败，请检查网络和 Chromium/Edge 浏览器后重试')
