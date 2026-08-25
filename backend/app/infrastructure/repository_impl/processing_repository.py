from typing import Optional
import logging

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class ProcessingRepository(BaseRepository):
    def log_processing(
        self,
        news_id: int | None,
        stage: str,
        action: str,
        details: Optional[str] = None,
        operation_id: Optional[str] = None,
    ):
        try:
            self.execute(
                'INSERT INTO processing_logs (news_id, stage, action, details, operation_id) VALUES (?, ?, ?, ?, ?)',
                (news_id, stage, action, details, operation_id),
            )
        except Exception:
            logger.exception("记录处理日志失败")

    def link_news_tag(self, news_id: int, tag_id: int, confidence: float = 0.9):
        try:
            self.execute(
                'INSERT OR IGNORE INTO news_tags (news_id, tag_id) VALUES (?, ?)',
                (news_id, tag_id),
            )
        except Exception:
            logger.exception("关联标签失败")
