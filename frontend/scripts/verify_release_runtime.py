from __future__ import annotations

import argparse
import base64
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright


class SpaHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        requested = Path(self.directory) / urlsplit(self.path).path.lstrip("/")
        if not requested.exists() or requested.is_dir():
            self.path = "/index.html"
        return super().do_GET()

    def log_message(self, _format, *_args):
        return


def fake_token() -> str:
    def encode(value: dict) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    return f"{encode({'alg': 'none', 'typ': 'JWT'})}.{encode({'sub': 'runtime-check', 'exp': int(time.time()) + 3600})}.check"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, default=Path(__file__).resolve().parents[1] / "dist")
    args = parser.parse_args()
    dist = args.dist.resolve()
    if not (dist / "index.html").is_file():
        raise SystemExit(f"release runtime check cannot find {dist / 'index.html'}")

    handler = partial(SpaHandler, directory=dist)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    failures: list[str] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context()
            context.add_init_script(f"localStorage.setItem('token', {json.dumps(fake_token())})")
            page = context.new_page()
            page.on("pageerror", lambda error: failures.append(f"pageerror: {error}"))
            page.route(
                "**/api/**",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"success": True, "data": {}}),
                ),
            )
            for path, selector in (("/", "main"), ("/login", "form"), ("/admin", ".ant-layout")):
                page.goto(base_url + path, wait_until="domcontentloaded")
                page.locator(selector).first.wait_for(state="visible", timeout=10_000)
                if path == "/admin" and page.url.endswith("/login"):
                    failures.append("admin route redirected to login during release smoke")
            context.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    if failures:
        raise SystemExit("release runtime check failed:\n" + "\n".join(failures))
    print("release runtime verified: public, login and admin routes rendered without page errors")


if __name__ == "__main__":
    main()
