"""Article identity shared by fixed-media collection and persistent storage."""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_MEDIA_HOSTS = {
    'www.techflowpost.com', 'techflowpost.com',
    'm.theblockbeats.info', 'www.theblockbeats.info', 'theblockbeats.info',
    'www.chaincatcher.com', 'chaincatcher.com',
    'www.panewslab.com', 'panewslab.com',
    'www.odaily.news', 'odaily.news', 'news.marsbit.co',
    'www.wublock123.com', 'wublock123.com', 'foresightnews.pro',
}
_TRACKING_KEYS = {'fbclid', 'gclid', 'dclid', 'msclkid'}


def source_identity(url: str) -> str:
    """Only canonicalize verified media aliases; keep meaningful URL components."""
    parts = urlsplit(url)
    host = (parts.hostname or '').lower()
    if parts.scheme.lower() not in {'http', 'https'} or host not in _MEDIA_HOSTS:
        # Other sources intentionally use query IDs, fragments or virtual URLs.
        return url
    if parts.username is not None or parts.password is not None:
        return url
    path = parts.path.rstrip('/') or '/'
    if host in {'www.techflowpost.com', 'techflowpost.com'}:
        path = re.sub(r'^/zh-CN/', '/', path)
    if host in {'m.theblockbeats.info', 'www.theblockbeats.info', 'theblockbeats.info'}:
        host = 'www.theblockbeats.info'
    port = parts.port
    custom_port = port is not None and not ((parts.scheme.lower() == 'http' and port == 80)
                                            or (parts.scheme.lower() == 'https' and port == 443))
    if custom_port:
        host += f':{port}'
    # Rebuild only when a recognized tracking parameter was actually removed.
    parameters = parse_qsl(parts.query, keep_blank_values=True)
    retained = [(key, value) for key, value in parameters
                if not key.lower().startswith('utm_') and key.lower() not in _TRACKING_KEYS]
    query = urlencode(retained) if len(retained) != len(parameters) else parts.query
    return urlunsplit((parts.scheme.lower() if custom_port else 'https', host, path, query, parts.fragment))
