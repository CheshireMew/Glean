from __future__ import annotations

import asyncio
import json
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Callable, Dict, Iterable

@dataclass(frozen=True)
class AIEndpoint:
    name: str
    api_key: str
    base_url: str
    model: str
    input_price_per_million: float = 0.0
    output_price_per_million: float = 0.0


class ResilientAIClient:
    def __init__(
        self,
        providers: Iterable[Dict],
        concurrency: int,
        throttle_seconds: float = 0.0,
        telemetry_observer: Callable[[Dict], None] | None = None,
    ):
        from openai import AsyncOpenAI

        self.endpoints = [AIEndpoint(**provider) for provider in providers]
        if not self.endpoints:
            raise ValueError("没有可用的 AI 端点")
        self.clients = {
            endpoint.name: AsyncOpenAI(
                api_key=endpoint.api_key,
                base_url=endpoint.base_url,
                max_retries=0,
                timeout=60.0,
            )
            for endpoint in self.endpoints
        }
        self.semaphore = asyncio.Semaphore(max(int(concurrency), 1))
        self.throttle_seconds = max(float(throttle_seconds), 0.0)
        self._throttle_lock = asyncio.Lock()
        self._last_request_at = 0.0
        self.telemetry_observer = telemetry_observer

    async def _wait_for_slot(self) -> None:
        if self.throttle_seconds <= 0:
            return
        async with self._throttle_lock:
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < self.throttle_seconds:
                await asyncio.sleep(self.throttle_seconds - elapsed)
            self._last_request_at = time.monotonic()

    @staticmethod
    def _parse_json(content: str) -> Dict:
        text = (content or "").strip()
        if text.startswith("```"):
            lines = text.splitlines()[1:]
            if lines and lines[-1].strip() == "```":
                lines.pop()
            text = "\n".join(lines).strip()
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("AI response must be a JSON object")
        return parsed

    def _observe(self, event: Dict) -> None:
        if not self.telemetry_observer:
            return
        try:
            self.telemetry_observer(event)
        except Exception:
            # Quality logging must not turn a usable AI response into a failed content job.
            return

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
        context: Dict | None = None,
    ) -> Dict:
        errors = []
        prompt_version = sha256(f"{system}\n---\n{user}".encode("utf-8")).hexdigest()[:20]
        context = dict(context or {})
        async with self.semaphore:
            for endpoint_index, endpoint in enumerate(self.endpoints):
                client = self.clients[endpoint.name]
                for attempt in range(3):
                    started_at = datetime.now(timezone.utc)
                    started_clock = time.perf_counter()
                    try:
                        await self._wait_for_slot()
                        response = await client.chat.completions.create(
                            model=endpoint.model,
                            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                            temperature=temperature,
                            max_tokens=max_tokens,
                        )
                        parsed = self._parse_json(response.choices[0].message.content or "{}")
                        usage = getattr(response, "usage", None)
                        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
                        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
                        cost = (
                            input_tokens * endpoint.input_price_per_million
                            + output_tokens * endpoint.output_price_per_million
                        ) / 1_000_000
                        completed_at = datetime.now(timezone.utc)
                        self._observe({
                            **context,
                            "provider_name": endpoint.name,
                            "model": endpoint.model,
                            "prompt_version": prompt_version,
                            "failover_index": endpoint_index,
                            "attempt": attempt + 1,
                            "started_at": started_at.isoformat(),
                            "completed_at": completed_at.isoformat(),
                            "duration_ms": round((time.perf_counter() - started_clock) * 1000),
                            "input_tokens": input_tokens,
                            "output_tokens": output_tokens,
                            "estimated_cost": cost,
                            "success": True,
                            "response_hash": sha256(
                                json.dumps(parsed, sort_keys=True, ensure_ascii=False).encode("utf-8")
                            ).hexdigest(),
                        })
                        return parsed
                    except Exception as exc:
                        errors.append(f"{endpoint.name} attempt {attempt + 1}: {exc}")
                        completed_at = datetime.now(timezone.utc)
                        self._observe({
                            **context,
                            "provider_name": endpoint.name,
                            "model": endpoint.model,
                            "prompt_version": prompt_version,
                            "failover_index": endpoint_index,
                            "attempt": attempt + 1,
                            "started_at": started_at.isoformat(),
                            "completed_at": completed_at.isoformat(),
                            "duration_ms": round((time.perf_counter() - started_clock) * 1000),
                            "success": False,
                            "error_type": type(exc).__name__,
                            "error_message": str(exc)[:2000],
                        })
                        if attempt < 2:
                            await asyncio.sleep(min(2 ** attempt + random.uniform(0, 0.5), 5.0))
        raise RuntimeError("; ".join(errors))

    async def close(self) -> None:
        await asyncio.gather(*(client.close() for client in self.clients.values()), return_exceptions=True)
