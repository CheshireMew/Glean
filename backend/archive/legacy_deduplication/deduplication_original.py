from __future__ import annotations

from .dedup_impl.local_deduplicator import LocalDeduplicator


def build_local_deduplicator(similarity_threshold: float, time_window_hours: int) -> LocalDeduplicator:
    return LocalDeduplicator(
        similarity_threshold=similarity_threshold,
        time_window_hours=time_window_hours,
    )
