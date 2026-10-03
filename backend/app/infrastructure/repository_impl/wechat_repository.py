from .base_repository import BaseRepository


class WechatRepository(BaseRepository):
    def list_sources(self, enabled_only=False):
        where = 'WHERE enabled = 1' if enabled_only else ''
        return [dict(row) for row in self.execute(
            f'SELECT * FROM wechat_sources {where} ORDER BY id'
        ).fetchall()]

    def get_source(self, source_id):
        row = self.execute('SELECT * FROM wechat_sources WHERE id = ?', (source_id,)).fetchone()
        return dict(row) if row else None

    def add_source(self, account):
        self.execute("""INSERT INTO wechat_sources (fake_id, name, alias, introduction)
            VALUES (?, ?, ?, ?) ON CONFLICT(fake_id) DO NOTHING""",
            (account['fake_id'], account['name'], account.get('alias', ''), account.get('introduction', '')))
        return dict(self.execute('SELECT * FROM wechat_sources WHERE fake_id = ?', (account['fake_id'],)).fetchone())

    def update_source(self, source_id, enabled, limit, interval):
        self.execute("""UPDATE wechat_sources SET enabled = ?, default_limit = ?,
            default_interval = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
            (int(enabled), limit, interval, source_id))
        return self.get_source(source_id)
