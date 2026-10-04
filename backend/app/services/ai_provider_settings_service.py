from __future__ import annotations

import json
from urllib.parse import urlparse

from shared.content_contract import integration_key
from ..core.coercion import non_negative_float, positive_int
from ..core.exceptions import ValidationError
from ..core.outbound_http import validate_url


class AIProviderSettingsService:
    def __init__(self, config_repository, transaction):
        self._config_repository = config_repository
        self._transaction = transaction

    def get_config(self, include_secrets: bool = False) -> dict:
        repo = self._config_repository()
        raw_providers = repo.get_config(integration_key("llm", "providers")) or "[]"
        try:
            providers = json.loads(raw_providers)
        except Exception:
            providers = []
        public_providers = providers if include_secrets else [
            {**provider, "api_key": "••••••••", "has_api_key": bool(provider.get("api_key"))}
            for provider in providers
        ]
        return {
            "providers": public_providers,
            "analysis_concurrency": positive_int(repo.get_config(integration_key("llm", "analysis_concurrency")), 3),
            "enrichment_concurrency": positive_int(repo.get_config(integration_key("llm", "enrichment_concurrency")), 2),
            "throttle_seconds": non_negative_float(repo.get_config(integration_key("llm", "throttle_seconds")), 0.0),
        }

    def set_config(self, config: dict) -> dict:
        providers = config.get("providers") or []
        if not providers:
            raise ValidationError("至少配置一个 AI 端点")
        existing = {
            provider.get("name"): provider
            for provider in self.get_config(include_secrets=True)["providers"]
        }
        names = set()
        for provider in providers:
            name = (provider.get("name") or "").strip()
            if not name or name in names:
                raise ValidationError("AI 端点名称不能为空或重复")
            supplied_key = provider.get("api_key") or ""
            if supplied_key == "••••••••":
                provider["api_key"] = (existing.get(name) or {}).get("api_key") or ""
            if not provider.get("api_key") or not provider.get("base_url") or not provider.get("model"):
                raise ValidationError(f"AI 端点 {name} 的配置不完整")
            parsed_url = urlparse(str(provider["base_url"]).strip())
            if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
                raise ValidationError(f"AI 端点 {name} 的地址必须是有效的 HTTP(S) URL")
            validate_url(provider['base_url'], 'integration')
            provider["name"] = name
            provider["base_url"] = str(provider["base_url"]).strip().rstrip("/")
            provider["model"] = str(provider["model"]).strip()
            names.add(name)
        with self._transaction() as repos:
            repo = repos.config
            repo.set_config(integration_key("llm", "providers"), json.dumps(providers, ensure_ascii=False))
            repo.set_config(integration_key("llm", "analysis_concurrency"), str(config.get("analysis_concurrency") or 3))
            repo.set_config(integration_key("llm", "enrichment_concurrency"), str(config.get("enrichment_concurrency") or 2))
            repo.set_config(integration_key("llm", "throttle_seconds"), str(config.get("throttle_seconds") or 0))
        return {"message": "配置已保存"}
