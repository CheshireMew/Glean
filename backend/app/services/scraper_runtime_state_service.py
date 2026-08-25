from __future__ import annotations

import json
from typing import Dict, Optional

from ..core.exceptions import ValidationError


class ScraperRuntimeStateService:
    def __init__(self, config_repository, scraper_state_repository, scraper_registry):
        self._config_repository = config_repository
        self._scraper_state_repository = scraper_state_repository
        self._scraper_registry = scraper_registry

    @staticmethod
    def _config_key(name: str) -> str:
        return f"scraper.{name}.runtime"

    def ensure_runtime_initialized(self) -> None:
        config_repo = self._config_repository()
        state_repo = self._scraper_state_repository()
        for definition in self._scraper_registry.list_definitions():
            name = definition.name
            if not config_repo.get_config(self._config_key(name)):
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
            return defaults.copy()
        try:
            return {**defaults, **json.loads(raw)}
        except Exception:
            return defaults.copy()

    def update_scraper_config(self, name: str, interval: Optional[str], limit: Optional[int]) -> Dict:
        self.ensure_runtime_initialized()
        self.require_scraper(name)
        config = self.get_scraper_config(name)
        if interval is not None:
            if interval == "manual":
                config.pop("interval", None)
            else:
                try:
                    interval_value = int(interval)
                except (TypeError, ValueError) as exc:
                    raise ValidationError("抓取频率必须是分钟数或 manual") from exc
                if interval_value < 5 or interval_value > 10080:
                    raise ValidationError("抓取频率必须在 5 到 10080 分钟之间")
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
            }
        return payload

    def set_scraper_state(self, name: str, payload: Dict) -> None:
        self._scraper_state_repository().update_state(name, payload)

    def append_log(self, name: str, message: str) -> None:
        self._scraper_state_repository().append_log(name, message)

    def append_logs(self, name: str, messages: list[str]) -> None:
        if messages:
            self._scraper_state_repository().append_logs(name, messages)
