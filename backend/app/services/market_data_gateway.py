from __future__ import annotations

from datetime import datetime, timezone

import httpx

from ..core.exceptions import BusinessError, ValidationError


class MarketDataGateway:
    BINANCE_BASE_URL = "https://api.binance.com"

    async def observe(self, instrument: dict, observed_at: datetime) -> dict:
        provider = instrument["provider"].lower()
        if provider != "binance":
            raise ValidationError(f"行情提供方 {provider} 不支持自动采集，请使用手工快照接口")
        symbol = f"{instrument['symbol']}{instrument['quote_symbol']}".upper()
        timestamp_ms = int(observed_at.astimezone(timezone.utc).timestamp() * 1000)
        try:
            async with httpx.AsyncClient(base_url=self.BINANCE_BASE_URL, timeout=15) as client:
                response = await client.get(
                    "/api/v3/klines",
                    params={"symbol": symbol, "interval": "1m", "startTime": timestamp_ms, "limit": 1},
                )
                response.raise_for_status()
                rows = response.json()
                if not rows:
                    raise BusinessError(f"Binance 没有返回 {symbol} 在该时点的行情")
                row = rows[0]
                return {
                    "observed_at": datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc).isoformat(),
                    "price": float(row[4]),
                    "volume": float(row[5]),
                    "metadata": {"provider": "binance", "symbol": symbol, "quote_volume": float(row[7])},
                }
        except httpx.HTTPStatusError as exc:
            raise BusinessError(f"Binance 行情请求失败（HTTP {exc.response.status_code}）") from exc
        except httpx.RequestError as exc:
            raise BusinessError(f"Binance 行情网络失败：{exc}") from exc
