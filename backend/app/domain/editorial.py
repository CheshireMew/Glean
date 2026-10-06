from __future__ import annotations

from ..core.exceptions import NotFoundError, ValidationError


def validate_draft_items(publication, content_type, items, get_entry):
    """The same membership rules apply before creating, editing or publishing a draft."""
    if not publication:
        raise NotFoundError("发布频道不存在")
    if publication["content_type"] != content_type:
        raise ValidationError("草稿内容类型与发布频道不一致")
    entry_ids = [int(item["review_entry_id"]) for item in items]
    if len(entry_ids) != len(set(entry_ids)):
        raise ValidationError("草稿不能重复包含同一条内容")
    for entry_id in entry_ids:
        entry = get_entry(entry_id)
        if not entry:
            raise NotFoundError(f"审核内容 {entry_id} 不存在")
        if entry.get("profile_slug") != publication["profile_slug"]:
            raise ValidationError(f"审核内容 {entry_id} 不属于该内容档案")
        if entry.get("content_type") != content_type:
            raise ValidationError(f"审核内容 {entry_id} 类型不一致")
