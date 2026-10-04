"""Production egress policy, pinned DNS destinations and bounded response bodies."""
import asyncio
import ipaddress
import socket
import zlib
from urllib.parse import urlsplit

import httpx

from .config import settings
from .exceptions import ValidationError

MAX_RESPONSE_BYTES = 4 * 1024 * 1024


def validate_url(url, purpose='source'):
    try:
        parsed = urlsplit(str(url))
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        raise ValidationError('外部地址无效')
    if parsed.scheme not in {'http', 'https'} or not host or parsed.username or parsed.password:
        raise ValidationError('外部地址必须是没有账号密码的 HTTP(S) URL')
    if settings.ENV == 'production':
        allowed = {value.strip().lower() for value in settings.PRIVATE_ENDPOINT_HOSTS.split(',') if value.strip()}
        if parsed.scheme != 'https' and purpose != 'source' and host.lower() not in allowed:
            raise ValidationError('生产环境外部凭据只能通过 HTTPS 发送；本机服务需明确允许主机名')
    return host, port or (443 if parsed.scheme == 'https' else 80)


def resolve_destination(url, purpose='source'):
    host, port = validate_url(url, purpose)
    allowed = {value.strip().lower() for value in settings.PRIVATE_ENDPOINT_HOSTS.split(',') if value.strip()}
    try:
        addresses = list(dict.fromkeys(item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)))
    except socket.gaierror:
        raise ValidationError('外部地址无法解析')
    explicit_private = purpose != 'source' and host.lower() in allowed
    for address in addresses:
        ip = ipaddress.ip_address(address)
        mapped = getattr(ip, 'ipv4_mapped', None)
        if not explicit_private and not (mapped or ip).is_global:
            raise ValidationError('外部请求禁止访问本机、内网或保留地址')
        if ip.is_unspecified or ip.is_multicast:
            raise ValidationError('外部地址不能是未指定地址或组播地址')
    if not addresses:
        raise ValidationError('外部地址没有可用地址')
    return host, addresses[0]


class SafeHTTPTransport(httpx.AsyncBaseTransport):
    def __init__(self, purpose='source', max_bytes=MAX_RESPONSE_BYTES):
        self.purpose = purpose
        self.max_bytes = max_bytes

    async def handle_async_request(self, request):
        validate_url(request.url, self.purpose)
        if settings.ENV == 'production':
            host, address = await asyncio.to_thread(resolve_destination, request.url, self.purpose)
            extensions = {**request.extensions, 'sni_hostname': host}
            outgoing = httpx.Request(request.method, request.url.copy_with(host=address),
                                     headers=request.headers, stream=request.stream, extensions=extensions)
        else:
            outgoing = request
        # A transport is scoped to one destination and response: pool reuse must
        # never mix distinct Host/SNI names that happen to resolve to the same IP.
        async with httpx.AsyncHTTPTransport(retries=0) as transport:
            response = await transport.handle_async_request(outgoing)
            try:
                declared = response.headers.get('content-length')
                if declared and int(declared) > self.max_bytes:
                    raise ValidationError('外部响应超过允许的大小')
                content = bytearray()
                if response.is_stream_consumed:
                    content.extend(response.content)
                    if len(content) > self.max_bytes:
                        raise ValidationError('外部响应超过允许的大小')
                else:
                    encoding = response.headers.get('content-encoding', 'identity').lower()
                    if encoding not in {'identity', 'gzip', 'deflate'}:
                        raise ValidationError('外部响应使用不支持的压缩格式')
                    decoder = zlib.decompressobj(31 if encoding == 'gzip' else 15) if encoding != 'identity' else None
                    received = 0
                    async for chunk in response.aiter_raw(chunk_size=65536):
                        received += len(chunk)
                        if received > self.max_bytes:
                            raise ValidationError('外部响应超过允许的大小')
                        part = decoder.decompress(chunk, self.max_bytes - len(content) + 1) if decoder else chunk
                        content.extend(part)
                        if len(content) > self.max_bytes:
                            raise ValidationError('外部响应超过允许的大小')
                    if decoder:
                        content.extend(decoder.flush(self.max_bytes - len(content) + 1))
                        if len(content) > self.max_bytes or not decoder.eof:
                            raise ValidationError('外部响应大小或压缩格式无效')
                headers = [(k, v) for k, v in response.headers.raw
                           if k.lower() not in {b'content-encoding', b'content-length'}]
                return httpx.Response(response.status_code, headers=headers, content=bytes(content),
                                      extensions=response.extensions)
            finally:
                await response.aclose()


def safe_http_client(purpose='source', **kwargs):
    headers = {'Accept-Encoding': 'identity', **kwargs.pop('headers', {})}
    return httpx.AsyncClient(transport=SafeHTTPTransport(purpose), trust_env=False, headers=headers,
                            follow_redirects=False, **kwargs)
