"""Request limits run before FastAPI parses bodies or opens database sessions."""
from collections import OrderedDict, deque
import asyncio
import re
import time

from starlette.responses import JSONResponse
from .config import settings


class HTTPSecurityMiddleware:
    def __init__(self, app):
        self.app = app
        self.clients = OrderedDict()
        self.global_requests = deque()
        self.slots = asyncio.Semaphore(64)

    def allowed(self, client, now):
        for bucket in (self.global_requests, self.clients.setdefault(client, deque())):
            while bucket and bucket[0] <= now - 60:
                bucket.popleft()
        bucket = self.clients[client]
        self.clients.move_to_end(client)
        while len(self.clients) > 4096:
            self.clients.popitem(last=False)
        if len(bucket) >= 120 or len(self.global_requests) >= 1200:
            return False
        bucket.append(now)
        self.global_requests.append(now)
        return True

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        path = scope['path']
        if settings.ENV == 'production' and path in {'/docs', '/redoc', '/openapi.json', '/docs/oauth2-redirect'}:
            return await JSONResponse({'detail': 'Not Found'}, status_code=404)(scope, receive, send)
        headers = dict(scope['headers'])
        request_id = headers.get(b'x-request-id', b'').decode('ascii', errors='ignore')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', request_id):
            scope['headers'] = [(k, v) for k, v in scope['headers'] if k != b'x-request-id']
        if settings.ENV == 'production' and path.startswith('/api/'):
            client = (scope.get('client') or ('unknown', 0))[0]
            if not self.allowed(client, time.monotonic()):
                return await JSONResponse({'detail': '请求过于频繁，请稍后重试'}, 429,
                                          headers={'Retry-After': '60'})(scope, receive, send)
        if path == '/api/login':
            origin = headers.get(b'origin', b'').decode()
            if origin and origin not in settings.ALLOWED_ORIGINS:
                return await JSONResponse({'detail': '不允许的登录来源'}, 403)(scope, receive, send)
        async def secure_send(message):
            if message['type'] == 'http.response.start':
                extras = [(b'x-content-type-options', b'nosniff'), (b'x-frame-options', b'DENY'),
                          (b'referrer-policy', b'strict-origin-when-cross-origin')]
                if path.startswith('/api/'):
                    extras.append((b'cache-control', b'no-store'))
                if settings.ENV == 'production':
                    extras.append((b'strict-transport-security', b'max-age=31536000'))
                names = {key for key, _ in extras}
                message['headers'] = [(key, value) for key, value in message['headers'] if key not in names] + extras
            await send(message)
        async with self.slots:
            if scope['method'] in {'POST', 'PUT', 'PATCH', 'DELETE'}:
                limit = 4096 if path == '/api/login' else 2 * 1024 * 1024
                try:
                    if int(headers.get(b'content-length', b'0')) > limit:
                        return await JSONResponse({'detail': '请求体过大'}, 413)(scope, receive, secure_send)
                except ValueError:
                    return await JSONResponse({'detail': '无效的请求长度'}, 400)(scope, receive, secure_send)
                body = bytearray()
                deadline = time.monotonic() + 15
                while True:
                    try:
                        message = await asyncio.wait_for(receive(), timeout=max(0.001, deadline - time.monotonic()))
                    except asyncio.TimeoutError:
                        return await JSONResponse({'detail': '请求体接收超时'}, 408)(scope, receive, secure_send)
                    if message['type'] == 'http.disconnect':
                        return
                    body.extend(message.get('body', b''))
                    if len(body) > limit:
                        return await JSONResponse({'detail': '请求体过大'}, 413)(scope, receive, secure_send)
                    if not message.get('more_body'):
                        break
                consumed = False
                async def buffered_receive():
                    nonlocal consumed
                    if not consumed:
                        consumed = True
                        return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
                    return await receive()
                return await self.app(scope, buffered_receive, secure_send)
            await self.app(scope, receive, secure_send)
