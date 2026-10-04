from __future__ import annotations

import json
import time
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from ..core.exceptions import BusinessError
from ..core.outbound_http import safe_http_client


def plain_text(value):
    return BeautifulSoup(str(value or ''), 'html.parser').get_text('\n', strip=True)


def article_url(value):
    """Keep stable article identity, dropping session/tracking parameters."""
    parsed = urlparse(str(value or '').replace('&amp;', '&'))
    if parsed.hostname != 'mp.weixin.qq.com' or parsed.scheme not in {'http', 'https'}:
        return ''
    allowed = {'__biz', 'mid', 'idx', 'sn'}
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parsed.query) if k in allowed))
    if parsed.path == '/s' and not {'__biz', 'mid', 'idx'}.issubset(dict(parse_qsl(query))):
        return ''
    if parsed.path != '/s' and not parsed.path.startswith('/s/'):
        return ''
    return urlunparse(('https', 'mp.weixin.qq.com', parsed.path, '', query, ''))


class WechatGateway:
    def __init__(self, load_session, mark_failure, reserve_request):
        self._load_session = load_session
        self._mark_failure = mark_failure
        self._reserve_request = reserve_request

    async def _request(self, path, params):
        import asyncio

        session = self._load_session()
        if not session.get('token') or session.get('state') == 'expired':
            raise BusinessError('公众号登录已失效或尚未登录，请到“公众号采集”扫码登录')
        await asyncio.sleep(self._reserve_request())
        # Another process can disconnect, refresh or hit a limit while this request waits.
        session = self._load_session()
        if not session.get('token') or session.get('state') == 'expired':
            raise BusinessError('公众号登录已失效或尚未登录，请到“公众号采集”扫码登录')
        if session.get('cooldown_until', 0) > time.time():
            raise BusinessError('微信限制了访问频率，稍后会自动恢复，请勿反复重试')
        cookies = httpx.Cookies()
        for cookie in session.get('cookies', []):
            cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain', 'mp.weixin.qq.com'),
                        path=cookie.get('path', '/'))
        headers = {'Referer': 'https://mp.weixin.qq.com/',
                   'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36'}
        try:
            async with safe_http_client('integration', cookies=cookies, headers=headers, timeout=25) as client:
                response = await client.get('https://mp.weixin.qq.com/cgi-bin/' + path,
                    params={**params, 'token': session['token'], 'lang': 'zh_CN', 'f': 'json', 'ajax': '1'})
            if response.status_code in {301, 302, 303, 401, 403}:
                self._mark_failure(session, 'expired', '微信登录已失效，请重新扫码')
                raise BusinessError('微信登录已失效，请重新扫码')
            if response.status_code == 429:
                self._mark_failure(session, 'limited', '微信限制了访问频率，暂停请求 30 分钟')
                raise BusinessError('微信限制了访问频率，暂停请求 30 分钟')
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError):
            raise BusinessError('微信公众号接口暂时无法访问，请稍后重试') from None
        if not isinstance(data, dict) or not isinstance(data.get('base_resp'), dict):
            raise BusinessError('微信公众号接口返回格式已变化，未将其视为空订阅')
        ret = data['base_resp'].get('ret')
        if ret == 200003:
            self._mark_failure(session, 'expired', '微信登录已失效，请重新扫码')
            raise BusinessError('微信登录已失效，请重新扫码')
        if ret == 200013:
            self._mark_failure(session, 'limited', '微信限制了访问频率，暂停请求 30 分钟')
            raise BusinessError('微信限制了访问频率，暂停请求 30 分钟')
        if ret != 0:
            raise BusinessError(f'微信公众号接口暂不可用（返回码 {ret}），请稍后重试')
        return data

    async def search(self, query, begin=0):
        data = await self._request('searchbiz', {'action': 'search_biz', 'query': query,
                                                 'begin': begin, 'count': 5})
        if not isinstance(data.get('list'), list):
            raise BusinessError('公众号搜索结果格式已变化')
        return {'accounts': [{'fake_id': str(row['fakeid']), 'name': plain_text(row.get('nickname')),
                               'alias': str(row.get('alias') or ''),
                               'introduction': plain_text(row.get('signature'))}
                              for row in data['list'] if row.get('fakeid') and row.get('nickname')],
                'has_more': begin + len(data['list']) < int(data.get('total', 0)), 'begin': begin}

    async def articles(self, fake_id, begin=0):
        data = await self._request('appmsgpublish', {'sub': 'list', 'sub_action': 'list_ex',
                                                    'fakeid': fake_id, 'begin': begin, 'count': 5})
        try:
            page = data['publish_page']
            page = json.loads(page) if isinstance(page, str) else page
            batches = page['publish_list']
            if not isinstance(batches, list):
                raise TypeError()
            items = []
            for batch in batches:
                info = batch['publish_info']
                info = json.loads(info) if isinstance(info, str) else info
                articles = info['appmsgex']
                if not isinstance(articles, list):
                    raise TypeError()
                for article in articles:
                    items.append({**article, 'create_time': article.get('create_time') or info.get('publish_time')})
            return items, len(batches) == 5
        except (KeyError, TypeError, ValueError):
            raise BusinessError('公众号文章列表格式已变化，采集已停止') from None
