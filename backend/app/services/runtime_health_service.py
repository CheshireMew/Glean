from __future__ import annotations

from typing import Dict

from ..core.runtime_keys import WORKER_LEASE_NAME, WORKER_READY_STATUSES

class RuntimeHealthService:
    def __init__(self, database_gateway, runtime_lease_repository, expected_version: str):
        self._database = database_gateway
        self._runtime_lease_repository = runtime_lease_repository
        self._expected_version = expected_version

    @staticmethod
    def liveness() -> Dict:
        return {"status": "alive"}

    def api_readiness(self) -> tuple[bool, Dict]:
        checks: Dict[str, Dict] = {}
        try:
            self._database.assert_schema_current()
            conn = self._database.connect()
            try:
                conn.execute("SELECT 1").fetchone()
                foreign_keys = int(conn.execute("PRAGMA foreign_keys").fetchone()[0])
                required = {"news", "content_events", "review_entries", "review_entries_fts"}
                present = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE name IN ('news','content_events','review_entries','review_entries_fts')"
                    ).fetchall()
                }
            finally:
                conn.close()
            checks["database"] = {
                "ready": foreign_keys == 1 and present == required,
                "foreign_keys": foreign_keys == 1,
                "schema_current": present == required,
            }
        except Exception as exc:
            checks["database"] = {"ready": False, "error": str(exc)}

        ready = all(check.get("ready") for check in checks.values())
        return ready, {"status": "ready" if ready else "not_ready", "checks": checks}

    def pipeline_readiness(self) -> tuple[bool, Dict]:
        api_ready, api_payload = self.api_readiness()
        checks = dict(api_payload["checks"])
        try:
            lease = self._runtime_lease_repository().get(WORKER_LEASE_NAME)
            if not lease:
                checks["worker"] = {"ready": False, "reason": "worker 尚未取得运行租约"}
            else:
                active = bool(lease["active"])
                version_matches = lease.get("owner_version") == self._expected_version
                runtime_status = lease.get("runtime_status")
                checks["worker"] = {
                    "ready": active and version_matches and runtime_status in WORKER_READY_STATUSES,
                    "instance_id": lease["owner_id"],
                    "lease_expires_at": lease["lease_expires_at"],
                    "version": lease.get("owner_version"),
                    "expected_version": self._expected_version,
                    "version_matches": version_matches,
                    "runtime_status": runtime_status,
                    "details": lease.get("status_details"),
                }
        except Exception as exc:
            checks["worker"] = {"ready": False, "error": str(exc)}

        ready = api_ready and all(check.get("ready") for check in checks.values())
        return ready, {"status": "ready" if ready else "not_ready", "checks": checks}

    def readiness(self) -> tuple[bool, Dict]:
        return self.pipeline_readiness()
