from __future__ import annotations

import json
import uuid
from typing import Dict

from shared.content_contract import REVIEW_STATUS_PROCESSING

from ..core.exceptions import ConflictError, NotFoundError, ValidationError


class EditorialWorkbenchService:
    def __init__(self, repository, transaction):
        self._repository = repository
        self._transaction = transaction

    @staticmethod
    def _decode_entry(entry: Dict) -> Dict:
        result = dict(entry)
        for source_field, target_field, fallback in (
            ("review_tags", "tags", []),
            ("enrichment_citations", "citations", []),
        ):
            raw = result.get(source_field)
            try:
                result[target_field] = json.loads(raw or "[]")
            except (TypeError, json.JSONDecodeError):
                result[target_field] = fallback
        return result

    def get_entry(self, entry_id: int) -> Dict:
        entry = self._repository().get_entry(entry_id)
        if not entry:
            raise NotFoundError("审核内容不存在")
        result = self._decode_entry(entry)
        result["revisions"] = self._repository().list_revisions(entry_id)
        result["feedback"] = self._repository().list_feedback(entry_id)
        return result

    @staticmethod
    def _normalize_changes(values: Dict) -> Dict:
        changes = dict(values)
        changes.pop("change_note", None)
        changes.pop("quality_score", None)
        if "review_tags" in changes:
            tags = [str(tag).strip() for tag in (changes["review_tags"] or []) if str(tag).strip()]
            changes["review_tags"] = json.dumps(list(dict.fromkeys(tags)), ensure_ascii=False)
        if "enrichment_citations" in changes:
            changes["enrichment_citations"] = json.dumps(
                changes["enrichment_citations"] or [], ensure_ascii=False
            )
        return changes

    def update_entry(self, entry_id: int, values: Dict, actor: str) -> Dict:
        note = values.get("change_note")
        quality_score = values.get("quality_score")
        normalized = self._normalize_changes(values)
        with self._transaction() as tx:
            repo = tx.editorial_workbench
            entry = repo.get_entry(entry_id)
            if not entry:
                raise NotFoundError("审核内容不存在")
            if entry.get("review_status") == REVIEW_STATUS_PROCESSING:
                raise ConflictError("内容正在由 AI 审核，完成后才能人工修改")
            actual_changes = {
                key: value for key, value in normalized.items() if entry.get(key) != value
            }
            if not actual_changes:
                return self.get_entry(entry_id)
            version = int(entry.get("editorial_version") or 0)
            if version == 0:
                version = 1
                repo.save_revision(entry, version, "system", [], "AI 生成原稿")
            next_version = version + 1
            repo.update_entry(entry_id, actual_changes, actor, next_version)
            updated = repo.get_entry(entry_id)
            if not updated:
                raise NotFoundError("审核内容不存在")
            repo.save_revision(updated, next_version, actor, actual_changes.keys(), note)
            repo.add_feedback(
                entry_id,
                "edited",
                actor,
                quality_score,
                actual_changes.keys(),
                note,
            )
        return self.get_entry(entry_id)

    def restore_revision(self, entry_id: int, revision_number: int, actor: str) -> Dict:
        with self._transaction() as tx:
            repo = tx.editorial_workbench
            entry = repo.get_entry(entry_id)
            revision = repo.get_revision(entry_id, revision_number)
            if not entry or not revision:
                raise NotFoundError("内容或修订版本不存在")
            snapshot = revision["snapshot"]
            changes = {
                field: snapshot.get(field)
                for field in repo.EDITABLE_FIELDS
                if field in snapshot and entry.get(field) != snapshot.get(field)
            }
            if not changes:
                return self.get_entry(entry_id)
            version = max(int(entry.get("editorial_version") or 0), 1) + 1
            repo.update_entry(entry_id, changes, actor, version)
            restored = repo.get_entry(entry_id)
            repo.save_revision(
                restored,
                version,
                actor,
                changes.keys(),
                f"恢复自修订版本 {revision_number}",
            )
            repo.add_feedback(
                entry_id,
                "edited",
                actor,
                None,
                changes.keys(),
                f"恢复自修订版本 {revision_number}",
            )
        return self.get_entry(entry_id)

    def add_feedback(self, entry_id: int, values: Dict, actor: str) -> Dict:
        if not self._repository().get_entry(entry_id):
            raise NotFoundError("审核内容不存在")
        feedback_id = self._repository().add_feedback(
            entry_id,
            values["outcome"],
            actor,
            values.get("quality_score"),
            values.get("changed_fields") or [],
            values.get("notes"),
            values.get("invocation_id"),
        )
        return {"id": feedback_id}

    def create_draft(self, values: Dict, actor: str) -> Dict:
        with self._transaction() as tx:
            repo = tx.editorial_workbench
            publication = repo.get_publication(values["publication_id"])
            if not publication:
                raise NotFoundError("发布频道不存在")
            if publication["content_type"] != values["content_type"]:
                raise ValidationError("草稿内容类型与发布频道不一致")
            items = values["items"]
            entry_ids = [item["review_entry_id"] for item in items]
            if len(entry_ids) != len(set(entry_ids)):
                raise ValidationError("草稿不能重复包含同一条内容")
            for entry_id in entry_ids:
                entry = repo.get_entry(entry_id)
                if not entry:
                    raise NotFoundError(f"审核内容 {entry_id} 不存在")
                if entry.get("profile_slug") != publication["profile_slug"]:
                    raise ValidationError(f"审核内容 {entry_id} 不属于该内容档案")
                if entry.get("content_type") != values["content_type"]:
                    raise ValidationError(f"审核内容 {entry_id} 类型不一致")
            draft_key = f"draft:{values['content_type']}:{uuid.uuid4().hex}"
            draft_id = repo.create_draft(
                draft_key,
                values["publication_id"],
                values["content_type"],
                values["title"],
                actor,
            )
            repo.replace_draft_items(draft_id, items)
        return self.get_draft(draft_id)

    def get_draft(self, draft_id: int) -> Dict:
        draft = self._repository().get_draft(draft_id)
        if not draft:
            raise NotFoundError("发布草稿不存在")
        return draft

    def list_drafts(self, status: str | None, limit: int) -> list[Dict]:
        return self._repository().list_drafts(status, limit)

    def update_draft(self, draft_id: int, values: Dict) -> Dict:
        with self._transaction() as tx:
            repo = tx.editorial_workbench
            draft = repo.get_draft(draft_id)
            if not draft:
                raise NotFoundError("发布草稿不存在")
            if draft["status"] in {"publishing", "published"}:
                raise ConflictError("正在发布或已经发布的草稿不能修改")
            items = values.pop("items", None)
            scheduled_at = values.get("scheduled_at")
            if scheduled_at is not None:
                values["scheduled_at"] = scheduled_at.isoformat()
            repo.update_draft(draft_id, **values)
            if items is not None:
                repo.replace_draft_items(draft_id, items)
        return self.get_draft(draft_id)

    def add_correction(self, values: Dict, actor: str) -> Dict:
        correction_id = self._repository().add_correction(
            values["correction_type"],
            values["message"],
            actor,
            report_id=values.get("report_id"),
            review_entry_id=values.get("review_entry_id"),
            event_id=values.get("event_id"),
        )
        return {"id": correction_id}
