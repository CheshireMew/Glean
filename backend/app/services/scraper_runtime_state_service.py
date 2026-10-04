from __future__ import annotations

import json
from typing import Dict, Optional

from ..core.exceptions import ValidationError


class ScraperRuntimeStateService:
    def __init__(self, config_repository, scraper_state_repository, scraper_registry, source_access=None):
        self._config_repository = config_repository
        self._scraper_state_repository = scraper_state_repository
        self._scraper_registry = scraper_registry
        self._source_access = source_access

    def get_source_cooldown(self, name: str, definition=None) -> Dict:
        if self._source_access is None:
            return {}
        definition = definition or self._scraper_registry.get(name)
        error = self._source_access.for_definition(definition) if definition else None
        return {"cooldown_until": error.until, "cooldown_reason": str(error)} if error else {}

    @staticmethod
    def _config_key(name: str) -> str:
        return f"scraper.{name}.runtime"

    def ensure_runtime_initialized(self) -> None:
        config_repo = self._config_repository()
        state_repo = self._scraper_state_repository()
        for definition in self._scraper_registry.list_definitions():
            name = definition.name
            if config_repo.get_config(self._config_key(name)) is None:
                defaults = {"limit": definition.default_limit, "interval": definition.default_interval}
                config_repo.set_config(self._config_key(name), json.dumps(defaults, ensure_ascii=False))
            state_repo.ensure_state(name)

    def require_scraper(self, name: str):
        return self._scraper_registry.require(name)

    def get_scraper_config(self, name: str, definition=None, raw_value: str | None = None) -> Dict:
        definition = definition or self._scraper_registry.get(name)
        defaults = {"limit": definition.default_limit, "interval": definition.default_interval} if definition else {"limit": 5, "interval": 60}
        raw = raw_value if raw_value is not None else self._config_repository().get_config(self._config_key(name))
        if not raw:
            return {**defaults, "interval": None}
        try:
            saved = json.loads(raw)
            if not isinstance(saved, dict):
                raise ValueError("采集配置必须是对象")
            # Missing interval is the legacy representation of manual mode.
            interval = saved.get("interval")
            minimum = 30 if name.startswith("wechat__") else 5
            if type(interval) is not int or not minimum <= interval <= 10080:
                interval = None
            limit = saved.get("limit", defaults["limit"])
            if type(limit) is not int or not 1 <= limit <= 100:
                limit = defaults["limit"]
            return {"limit": limit, "interval": interval}
        except (ValueError, TypeError):
            return {**defaults, "interval": None}

    def update_scraper_config(self, name: str, interval: Optional[str], limit: Optional[int]) -> Dict:
        self.ensure_runtime_initialized()
        self.require_scraper(name)
        config = self.get_scraper_config(name)
        if interval is not None:
            if interval == "manual":
                config["interval"] = None
            else:
                try:
                    interval_value = int(interval)
                except (TypeError, ValueError) as exc:
                    raise ValidationError("抓取频率必须是分钟数或 manual") from exc
                if interval_value < 5 or interval_value > 10080:
                    raise ValidationError("抓取频率必须在 5 到 10080 分钟之间")
                if name.startswith('wechat__') and interval_value < 30:
                    raise ValidationError('公众号采集间隔至少为 30 分钟')
                config["interval"] = interval_value
        if limit is not None:
            if limit < 1 or limit > 100:
                raise ValidationError("抓取条数必须在 1 到 100 之间")
            config["limit"] = limit
        self._config_repository().set_config(self._config_key(name), json.dumps(config, ensure_ascii=False))
        return {"status": "success", "config": config}

    def get_spiders(self) -> Dict:
        return {
            "spiders": [
                {
                    "name": definition.name,
                    "display_name": definition.display_name,
                    "source_site": definition.source_site,
                    "type": definition.content_kind,
                    "source_type": definition.source_type,
                    "transport_kind": definition.transport_kind,
                }
                for definition in self._scraper_registry.list_definitions()
            ]
        }

    def get_scraper_state(self, name: str) -> Dict:
        self.require_scraper(name)
        return self._scraper_state_repository().get_state(name)

    def get_spider_status(self) -> Dict:
        definitions = self._scraper_registry.list_definitions()
        states = self._scraper_state_repository().list_states()
        configs = self._config_repository().get_by_prefix("scraper.")
        payload = {}
        for definition in definitions:
            name = definition.name
            payload[name] = {
                **states.get(name, {"scraper_name": name, "status": "idle", "logs": [], "items_scraped": 0}),
                **self.get_scraper_config(name, definition, configs.get(self._config_key(name))),
                **self.get_source_cooldown(name, definition),
                "refresh_on_view": False,
            }
        return payload

    def set_scraper_state(self, name: str, payload: Dict) -> None:
        self._scraper_state_repository().update_state(name, payload)

    def append_log(self, name: str, message: str) -> None:
        self._scraper_state_repository().append_log(name, message)

    def append_logs(self, name: str, messages: list[str]) -> None:
        if messages:
            self._scraper_state_repository().append_logs(name, messages)
