from __future__ import annotations

from ..core.exceptions import ConflictError, NotFoundError, ServiceUnavailableError
from ..domain.ai_sources import PUBLIC_AI_SOURCES


class AIRefreshService:
    """Refresh the fixed public sources on demand, coalescing all readers."""

    FRESHNESS_SECONDS = 300

    def __init__(self, commands):
        self._commands = commands

    async def refresh(self):
        sources = []
        for source in PUBLIC_AI_SOURCES:
            try:
                result = await self._commands.request_run(
                    source["key"], source.get("limit", 20),
                    freshness_seconds=source.get("freshness_seconds", self.FRESHNESS_SECONDS), trigger="ai-view")
                status = "updating" if result["status"] in {"accepted", "updating"} else result["status"]
                message = result.get("message", "") if status == "error" else ""
            except NotFoundError:
                status, message = "disabled", "来源已停用"
            except ConflictError as exc:
                status, message = "paused", str(exc)
            except ServiceUnavailableError:
                return {"updating": False, "message": "更新服务暂未运行，正在显示已保存的内容。", "sources": []}
            sources.append({"key": source["key"], "name": source["name"], "status": status, "message": message})
        return {"updating": any(item["status"] == "updating" for item in sources),
                "message": "", "sources": sources}
