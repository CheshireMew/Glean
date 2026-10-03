from __future__ import annotations

from ...domain.ai_sources import ai_source_sql


def published_entry_sql(alias: str = "r") -> str:
    """Website publication is evidenced by its saved report, independently of delivery."""
    return f"""(NOT {ai_source_sql(f'{alias}.source_site')} AND ({alias}.delivery_status = 'sent' OR EXISTS (
        SELECT 1 FROM daily_report_items web_item
        JOIN daily_reports web_report ON web_report.id = web_item.report_id
        JOIN profile_publications web_publication ON web_publication.id = web_report.publication_id
        WHERE web_item.review_entry_id = {alias}.id
          AND web_report.profile_slug = {alias}.profile_slug
          AND web_publication.enabled = 1 AND web_publication.is_public = 1
          AND (web_report.draft_id IS NULL OR EXISTS (
              SELECT 1 FROM publication_drafts web_draft
              WHERE web_draft.id = web_report.draft_id AND web_draft.status = 'published'
          ))
    )))"""
