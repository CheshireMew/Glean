from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import sqlite3
import uuid

from .repository_impl.api_key_repository import ApiKeyRepository
from .repository_impl.ai_quality_repository import AIQualityRepository
from .repository_impl.analyst_subscription_repository import AnalystSubscriptionRepository
from .repository_impl.archive_repository import ArchiveRepository
from .repository_impl.archive_query_repository import ArchiveQueryRepository
from .repository_impl.blacklist_repository import BlacklistRepository
from .repository_impl.config_repository import ConfigRepository
from .repository_impl.content_query_repository import ContentQueryRepository
from .repository_impl.daily_report_repository import DailyReportRepository
from .repository_impl.delivery_execution_repository import DeliveryExecutionRepository
from .repository_impl.delivery_repository import DeliveryOperationRepository
from .repository_impl.event_repository import EventRepository
from .repository_impl.event_query_repository import EventQueryRepository
from .repository_impl.editorial_profile_repository import EditorialProfileRepository
from .repository_impl.editorial_workbench_repository import EditorialWorkbenchRepository
from .repository_impl.event_intelligence_repository import EventIntelligenceRepository
from .repository_impl.intelligence_catalog_repository import IntelligenceCatalogRepository
from .repository_impl.market_intelligence_repository import MarketIntelligenceRepository
from .repository_impl.news_admin_repository import NewsAdminRepository
from .repository_impl.news_repository import NewsRepository
from .repository_impl.news_runtime_repository import NewsRuntimeRepository
from .repository_impl.maintenance_repository import MaintenanceRepository
from .repository_impl.push_repository import PushRepository
from .repository_impl.processing_repository import ProcessingRepository
from .repository_impl.publication_repository import PublicationRepository
from .repository_impl.rss_source_repository import RssSourceRepository
from .repository_impl.runtime_lease_repository import RuntimeLeaseRepository
from .repository_impl.review_admin_repository import ReviewAdminRepository
from .repository_impl.review_delivery_repository import ReviewDeliveryRepository
from .repository_impl.review_public_repository import ReviewPublicRepository
from .repository_impl.review_repository import ReviewRepository
from .repository_impl.scraper_command_repository import ScraperCommandRepository
from .repository_impl.scraper_state_repository import ScraperStateRepository
from .repository_impl.source_operations_repository import SourceOperationsRepository
from .repository_impl.tag_repository import TagRepository

from .database import database
from .lease_fencing import assert_current_operation_lease


class RepositoryUnitOfWork:
    """Transaction-scoped repository set used only at composition and transaction boundaries."""

    def __init__(self, conn: sqlite3.Connection | None = None):
        source = conn or database
        self.connection = conn
        self.config = ConfigRepository(source)
        self.content_queries = ContentQueryRepository(source, database.connect)
        self.news = NewsRepository(source)
        self.news_admin = NewsAdminRepository(source)
        self.news_runtime = NewsRuntimeRepository(source)
        self.maintenance = MaintenanceRepository(source)
        self.archive = ArchiveRepository(source)
        self.archive_query = ArchiveQueryRepository(source)
        self.review = ReviewRepository(source)
        self.review_admin = ReviewAdminRepository(source)
        self.review_delivery = ReviewDeliveryRepository(source)
        self.review_public = ReviewPublicRepository(source)
        self.blacklist = BlacklistRepository(source)
        self.api_keys = ApiKeyRepository(source)
        self.ai_quality = AIQualityRepository(source)
        self.analyst_subscriptions = AnalystSubscriptionRepository(source)
        self.push = PushRepository(source)
        self.processing = ProcessingRepository(source)
        self.publications = PublicationRepository(source)
        self.daily_reports = DailyReportRepository(source)
        self.delivery_operations = DeliveryOperationRepository(source)
        self.delivery_execution = DeliveryExecutionRepository(source)
        self.events = EventRepository(source)
        self.event_queries = EventQueryRepository(source)
        self.editorial_profiles = EditorialProfileRepository(source)
        self.editorial_workbench = EditorialWorkbenchRepository(source)
        self.event_intelligence = EventIntelligenceRepository(source)
        self.intelligence_catalog = IntelligenceCatalogRepository(source)
        self.market_intelligence = MarketIntelligenceRepository(source)
        self.source_operations = SourceOperationsRepository(source)
        self.scraper_state = ScraperStateRepository(source)
        self.scraper_commands = ScraperCommandRepository(source)
        self.rss_sources = RssSourceRepository(source)
        self.runtime_leases = RuntimeLeaseRepository(source)
        self.tags = TagRepository(source)


_current_repositories: ContextVar[RepositoryUnitOfWork | None] = ContextVar("current_repositories", default=None)


class RepositorySession:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.repos = RepositoryUnitOfWork(conn)


def repositories(conn: sqlite3.Connection | None = None) -> RepositoryUnitOfWork:
    if conn is not None:
        return RepositoryUnitOfWork(conn)
    current = _current_repositories.get()
    if current is not None:
        return current
    return RepositoryUnitOfWork(conn)


@contextmanager
def repository_session():
    conn = database.connect()
    token = None
    try:
        session = RepositorySession(conn)
        token = _current_repositories.set(session.repos)
        yield session
    finally:
        if token is not None:
            _current_repositories.reset(token)
        conn.close()


@contextmanager
def transactional_repositories():
    current = _current_repositories.get()
    if current is not None and current.connection is not None:
        conn = current.connection
        if conn.in_transaction:
            savepoint = f"glean_{uuid.uuid4().hex}"
            conn.execute(f"SAVEPOINT {savepoint}")
            try:
                yield current
                assert_current_operation_lease(conn)
                conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            except Exception:
                conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                conn.execute(f"RELEASE SAVEPOINT {savepoint}")
                raise
            return
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield current
            assert_current_operation_lease(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return
    with repository_session() as session:
        try:
            session.conn.execute("BEGIN IMMEDIATE")
            yield session.repos
            assert_current_operation_lease(session.conn)
            session.conn.commit()
        except Exception:
            session.conn.rollback()
            raise
