"""Persist reservations before a billable request, including retries and fallbacks."""
from datetime import datetime, timezone
import json
import math

from ..core.config import settings
from ..core.exceptions import ValidationError


class AIBudget:
    def __init__(self, transaction):
        self._transaction = transaction

    def reserve(self, endpoint, system, user, max_tokens):
        if settings.ENV != 'production':
            return None
        if settings.AI_DAILY_MAX_CALLS < 1 or not math.isfinite(settings.AI_DAILY_MAX_COST) or settings.AI_DAILY_MAX_COST <= 0:
            raise ValidationError('生产环境 AI 调用及费用上限必须大于零')
        prices = (endpoint.input_price_per_million, endpoint.output_price_per_million)
        if any(not math.isfinite(price) or price < 0 for price in prices) or max_tokens < 1:
            raise ValidationError('AI 价格及输出上限无效')
        # UTF-8 byte count is a conservative input-token bound. Reserve maximum
        # output before sending so concurrent jobs cannot overrun the daily budget.
        input_bound = len((system + user).encode('utf-8')) + 512
        cost = (input_bound * endpoint.input_price_per_million + max_tokens * endpoint.output_price_per_million) / 1_000_000
        allowed = {v.strip().lower() for v in settings.PRIVATE_ENDPOINT_HOSTS.split(',') if v.strip()}
        from urllib.parse import urlsplit
        if urlsplit(endpoint.base_url).hostname not in allowed and (
            endpoint.input_price_per_million <= 0 or endpoint.output_price_per_million <= 0
        ):
            raise ValidationError('生产环境远程 AI 端点必须填写输入、输出价格，才能执行费用上限')
        key = 'security.ai-budget.' + datetime.now(timezone.utc).date().isoformat()
        with self._transaction() as repos:
            value = json.loads(repos.config.get_config(key) or '{"calls":0,"cost":0}')
            if value['calls'] >= settings.AI_DAILY_MAX_CALLS or value['cost'] + cost > settings.AI_DAILY_MAX_COST:
                raise ValidationError('已达到当天 AI 调用或费用上限，停止请求')
            value['calls'] += 1
            value['cost'] += cost
            repos.config.set_config(key, json.dumps(value))
        return key, cost


    def settle(self, reservation, actual_cost):
        if not reservation:
            return
        if not math.isfinite(actual_cost) or actual_cost < 0:
            return  # Invalid provider usage cannot refund a reservation.
        key, reserved = reservation
        with self._transaction() as repos:
            value = json.loads(repos.config.get_config(key))
            value['cost'] = max(0, value['cost'] - reserved + actual_cost)
            repos.config.set_config(key, json.dumps(value))
