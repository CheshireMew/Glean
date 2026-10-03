from __future__ import annotations

import json
import time

from ..core.exceptions import BusinessError, NotFoundError, ValidationError
from ..domain.wechat import wechat_runtime_name, wechat_source_name


class WechatSourceService:
    SESSION_KEY = 'integration.wechat.session'
    GATE_KEY = 'integration.wechat.next_request'

    def __init__(self, repository, config_repository, transaction, login):
        self._repository = repository
        self._config_repository = config_repository
        self._transaction = transaction
        self._login = login

    def load_session(self):
        return json.loads(self._config_repository().get_config(self.SESSION_KEY) or '{}')

    def save_session(self, session):
        with self._transaction() as repos:
            repos.config.set_config(self.SESSION_KEY, json.dumps({**session, 'state': 'connected',
                                                               'message': '', 'cooldown_until': 0}))

    def mark_failure(self, session, state, message):
        with self._transaction() as repos:
            current = json.loads(repos.config.get_config(self.SESSION_KEY) or '{}')
            if current.get('session_id') != session.get('session_id'):
                return
            current.update(state=state, message=message,
                           cooldown_until=time.time() + 1800 if state == 'limited' else 0)
            repos.config.set_config(self.SESSION_KEY, json.dumps(current))

    def reserve_request(self):
        # Serialize request slots across the API process and the existing worker.
        with self._transaction() as repos:
            session = json.loads(repos.config.get_config(self.SESSION_KEY) or '{}')
            now = time.time()
            if session.get('cooldown_until', 0) > now:
                raise BusinessError('微信限制了访问频率，稍后会自动恢复，请勿反复重试')
            slot = max(now, float(repos.config.get_config(self.GATE_KEY) or 0))
            if slot - now > 20:
                raise BusinessError('公众号请求正在排队，请稍后重试')
            repos.config.set_config(self.GATE_KEY, str(slot + 3))
            return slot - now

    def status(self):
        session = self.load_session()
        state = session.get('state', 'disconnected')
        if state == 'limited' and session.get('cooldown_until', 0) <= time.time():
            state = 'connected'
        return {'state': state, 'saved_at': session.get('saved_at'),
                'message': session.get('message', '') if state != 'connected' else '',
                'cooldown_until': session.get('cooldown_until', 0), 'login': self._login.snapshot()}

    def start_login(self):
        return self._login.start(self.save_session)

    async def cancel_login(self):
        import asyncio

        if not await asyncio.to_thread(self._login.close):
            raise BusinessError('正在关闭上一次登录，请稍后重试')
        return self.status()

    async def disconnect(self):
        await self.cancel_login()
        # Clearing the locally stored session doesn't delete articles or subscriptions.
        self._config_repository().set_config(self.SESSION_KEY, '{}')
        return self.status()

    def list_sources(self, enabled_only=False):
        return [{**row, 'runtime_name': wechat_runtime_name(row['id']),
                 'source_site': wechat_source_name(row['name'])}
                for row in self._repository().list_sources(enabled_only)]

    def add_source(self, account):
        name = account['name'].strip()
        fake_id = account['fake_id'].strip()
        if not name or not fake_id:
            raise ValidationError('公众号名称和账号标识不能为空')
        with self._transaction() as repos:
            if any(row['name'] == name and row['fake_id'] != fake_id for row in repos.wechat.list_sources()):
                raise BusinessError('已有同名公众号，请先核对账号')
            return repos.wechat.add_source({**account, 'name': name, 'fake_id': fake_id})

    def update_source(self, source_id, payload):
        with self._transaction() as repos:
            if not repos.wechat.get_source(source_id):
                raise NotFoundError('公众号不存在')
            name = wechat_runtime_name(source_id)
            if repos.scraper_state.is_active(name):
                raise BusinessError('公众号正在采集，请等采集结束后修改')
            result = repos.wechat.update_source(source_id, payload['enabled'],
                                                payload['default_limit'], payload['default_interval'])
            repos.config.set_config(f'scraper.{name}.runtime', json.dumps({
                'limit': payload['default_limit'], 'interval': payload['default_interval']}))
            return result
