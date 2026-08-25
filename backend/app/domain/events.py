from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def event_primary_score(item: Mapping[str, Any]) -> tuple[int, int, str]:
    """Canonical source ranking used both when clustering and when replacing a deleted primary."""
    return (
        int(bool(item.get("is_marked_important"))),
        len(str(item.get("content") or "")),
        str(item.get("published_at") or ""),
    )


def select_event_primary(sources: Iterable[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    rows = list(sources)
    return max(rows, key=event_primary_score) if rows else None
