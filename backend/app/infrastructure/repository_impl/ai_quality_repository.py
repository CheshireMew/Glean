from __future__ import annotations

import json
from typing import Dict, Optional

from .base_repository import BaseRepository


class AIQualityRepository(BaseRepository):
    def record_invocation(self, event: Dict) -> int:
        cursor = self.execute(
            """
            INSERT INTO ai_invocations(
                operation_id, review_entry_id, event_id, profile_slug, stage,
                provider_name, model, prompt_version, failover_index, attempt,
                started_at, completed_at, duration_ms, input_tokens, output_tokens,
                estimated_cost, success, error_type, error_message, response_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.get("operation_id"),
                event.get("review_entry_id"),
                event.get("event_id"),
                event.get("profile_slug"),
                event.get("stage", "review"),
                event.get("provider_name") or "unknown",
                event.get("model") or "unknown",
                event.get("prompt_version") or "unknown",
                int(event.get("failover_index") or 0),
                int(event.get("attempt") or 1),
                event.get("started_at"),
                event.get("completed_at"),
                event.get("duration_ms"),
                event.get("input_tokens"),
                event.get("output_tokens"),
                event.get("estimated_cost"),
                bool(event.get("success")),
                event.get("error_type"),
                event.get("error_message"),
                event.get("response_hash"),
            ),
        )
        return int(cursor.lastrowid)

    def list_invocations(
        self,
        page: int,
        limit: int,
        days: int,
        stage: str | None,
        provider_name: str | None,
        profile_slug: str | None,
        success: bool | None,
    ) -> Dict:
        where = ["started_at >= datetime('now', ?)"]
        params: list[object] = [f"-{days} days"]
        for column, value in (
            ("stage", stage),
            ("provider_name", provider_name),
            ("profile_slug", profile_slug),
        ):
            if value:
                where.append(f"{column} = ?")
                params.append(value)
        if success is not None:
            where.append("success = ?")
            params.append(bool(success))
        return self.paginated_query(
            "ai_invocations",
            page,
            limit,
            where=" AND ".join(where),
            where_params=tuple(params),
            order_by="started_at DESC, id DESC",
        )

    def get_summary(self, days: int) -> Dict:
        params = (f"-{days} days",)
        overall = self.execute(
            """
            SELECT COUNT(*) AS calls,
                   SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS successes,
                   AVG(duration_ms) AS average_duration_ms,
                   COALESCE(SUM(input_tokens), 0) AS input_tokens,
                   COALESCE(SUM(output_tokens), 0) AS output_tokens,
                   COALESCE(SUM(estimated_cost), 0) AS estimated_cost,
                   COUNT(DISTINCT prompt_version) AS prompt_versions
            FROM ai_invocations WHERE started_at >= datetime('now', ?)
            """,
            params,
        ).fetchone()
        groups = [
            dict(row)
            for row in self.execute(
                """
                SELECT provider_name, model, stage, COUNT(*) AS calls,
                       SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS successes,
                       AVG(duration_ms) AS average_duration_ms,
                       COALESCE(SUM(input_tokens + output_tokens), 0) AS total_tokens,
                       COALESCE(SUM(estimated_cost), 0) AS estimated_cost
                FROM ai_invocations
                WHERE started_at >= datetime('now', ?)
                GROUP BY provider_name, model, stage
                ORDER BY calls DESC
                """,
                params,
            ).fetchall()
        ]
        feedback = [
            dict(row)
            for row in self.execute(
                """
                SELECT outcome, COUNT(*) AS count, COUNT(quality_score) AS scored_count,
                       AVG(quality_score) AS average_quality_score
                FROM ai_feedback
                WHERE created_at >= datetime('now', ?)
                GROUP BY outcome ORDER BY count DESC
                """,
                params,
            ).fetchall()
        ]
        feedback_counts = {item["outcome"]: int(item["count"]) for item in feedback}
        feedback_total = sum(feedback_counts.values())
        feedback_summary = {
            "total": feedback_total,
            "accepted": feedback_counts.get("accepted", 0),
            "edited": feedback_counts.get("edited", 0),
            "rejected": feedback_counts.get("rejected", 0),
            "incorrect": feedback_counts.get("incorrect", 0),
            "adoption_rate": (
                (feedback_counts.get("accepted", 0) + feedback_counts.get("edited", 0))
                / feedback_total
                if feedback_total
                else None
            ),
            "edit_rate": feedback_counts.get("edited", 0) / feedback_total if feedback_total else None,
            "rejection_rate": feedback_counts.get("rejected", 0) / feedback_total if feedback_total else None,
            "incorrect_rate": feedback_counts.get("incorrect", 0) / feedback_total if feedback_total else None,
            "average_quality_score": (
                sum(
                    float(item["average_quality_score"]) * int(item["scored_count"])
                    for item in feedback
                    if item.get("average_quality_score") is not None
                )
                / sum(
                    int(item["scored_count"])
                    for item in feedback
                    if item.get("average_quality_score") is not None
                )
                if any(item.get("average_quality_score") is not None for item in feedback)
                else None
            ),
        }
        total = dict(overall) if overall else {}
        calls = int(total.get("calls") or 0)
        successes = int(total.get("successes") or 0)
        total["success_rate"] = successes / calls if calls else None
        return {
            "days": days,
            "overall": total,
            "groups": groups,
            "feedback": feedback,
            "feedback_summary": feedback_summary,
        }

    def list_evaluation_cases(self, enabled: bool | None = None) -> list[Dict]:
        where = "WHERE enabled = ?" if enabled is not None else ""
        params = (bool(enabled),) if enabled is not None else ()
        rows = self.execute(
            f"SELECT * FROM ai_evaluation_cases {where} ORDER BY content_type, stage, name",
            params,
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["input"] = json.loads(item.pop("input_json") or "{}")
            item["expected"] = json.loads(item.pop("expected_json") or "{}")
            result.append(item)
        return result

    def get_evaluation_case(self, case_id: int) -> Optional[Dict]:
        row = self.execute("SELECT * FROM ai_evaluation_cases WHERE id = ?", (case_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["input"] = json.loads(item.pop("input_json") or "{}")
        item["expected"] = json.loads(item.pop("expected_json") or "{}")
        return item

    def save_evaluation_case(self, values: Dict, case_id: int | None = None) -> int:
        payload = (
            values["name"],
            values["content_type"],
            values["stage"],
            json.dumps(values["input"], ensure_ascii=False),
            json.dumps(values["expected"], ensure_ascii=False),
            bool(values.get("enabled", True)),
        )
        if case_id is None:
            cursor = self.execute(
                """
                INSERT INTO ai_evaluation_cases(
                    name, content_type, stage, input_json, expected_json, enabled
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                payload,
            )
            return int(cursor.lastrowid)
        cursor = self.execute(
            """
            UPDATE ai_evaluation_cases
            SET name = ?, content_type = ?, stage = ?, input_json = ?, expected_json = ?,
                enabled = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (*payload, case_id),
        )
        return case_id if cursor.rowcount > 0 else 0

    def save_evaluation_run(
        self,
        run_key: str,
        case_id: int,
        provider_name: str,
        model: str,
        prompt_version: str,
        result: Dict,
        metrics: Dict,
        passed: bool,
    ) -> int:
        cursor = self.execute(
            """
            INSERT INTO ai_evaluation_runs(
                run_key, case_id, provider_name, model, prompt_version,
                result_json, metrics_json, passed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_key,
                case_id,
                provider_name,
                model,
                prompt_version,
                json.dumps(result, ensure_ascii=False),
                json.dumps(metrics, ensure_ascii=False),
                bool(passed),
            ),
        )
        return int(cursor.lastrowid)

    def list_evaluation_runs(self, run_key: str | None = None, limit: int = 200) -> list[Dict]:
        where = "WHERE r.run_key = ?" if run_key else ""
        params = (run_key, limit) if run_key else (limit,)
        rows = self.execute(
            f"""
            SELECT r.*, c.name AS case_name, c.content_type, c.stage
            FROM ai_evaluation_runs r JOIN ai_evaluation_cases c ON c.id = r.case_id
            {where} ORDER BY r.created_at DESC, r.id DESC LIMIT ?
            """,
            params,
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["result"] = json.loads(item.pop("result_json") or "{}")
            item["metrics"] = json.loads(item.pop("metrics_json") or "{}")
            result.append(item)
        return result
