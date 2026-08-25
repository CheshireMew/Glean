from __future__ import annotations

from .infrastructure.database import database
from .infrastructure.repositories import repositories, transactional_repositories
from .infrastructure.event_clustering import build_event_clusterer
from .infrastructure.scraper_impl.rss_feed import RssFeedScraper
from .infrastructure.scrapers import scraper_catalog
from .core.config import settings
from .services.ai_pipeline_service import AIPipelineService
from .services.ai_provider_settings_service import AIProviderSettingsService
from .services.ai_quality_service import AIQualityService
from .services.analyst_access_service import AnalystAccessService
from .services.analyst_data_service import AnalystDataService
from .services.analyst_subscription_service import AnalystSubscriptionService
from .services.auth_management import CredentialService
from .services.auth_service import AuthService
from .services.automation_runtime_service import AutomationRuntimeService
from .services.automation_settings_service import AutomationSettingsService
from .services.blacklist_service import BlacklistService
from .services.content_lifecycle_service import ContentLifecycleService
from .services.content_service import ContentService
from .services.content_transition_service import ContentTransitionService
from .services.daily_report_service import DailyReportService
from .services.daily_delivery_service import DailyDeliveryService
from .services.data_maintenance_service import DataMaintenanceService
from .services.delivery_operation_service import DeliveryOperationService
from .services.delivery_retry_service import DeliveryRetryService
from .services.delivery_settings_service import DeliverySettingsService
from .services.digest_planner_service import DigestPlannerService
from .services.editorial_profile_service import EditorialProfileService
from .services.editorial_workbench_service import EditorialWorkbenchService
from .services.event_clustering_service import EventClusteringService
from .services.event_intelligence_service import EventIntelligenceService
from .services.intelligence_catalog_service import IntelligenceCatalogService
from .services.market_data_gateway import MarketDataGateway
from .services.market_intelligence_service import MarketIntelligenceService
from .services.operation_lease_service import OperationLeaseService
from .services.pipeline_orchestrator import PipelineOrchestrator
from .services.publication_service import PublicationService
from .services.publication_channel_gateway import PublicationChannelGateway
from .services.publication_workflow_service import PublicationWorkflowService
from .services.public_content_service import PublicContentService
from .services.review_settings_service import ReviewSettingsService
from .services.rss_source_service import RssSourceService
from .services.runtime_health_service import RuntimeHealthService
from .services.scraper_command_service import ScraperCommandService
from .services.scraper_registry_service import RegisteredScraper, ScraperRegistryService
from .services.scraper_run_service import ScraperRunService
from .services.scraper_runtime_state_service import ScraperRuntimeStateService
from .services.scraper_schedule_service import ScraperScheduleService
from .services.system_settings_service import SystemSettingsService
from .services.system_configuration_service import SystemConfigurationService
from .services.source_operations_service import SourceOperationsService
from .services.entry_delivery_service import AutomaticEntryDeliveryService, ManualEntryDeliveryService
from .services.telegram_delivery_service import TelegramAutomationDeliveryService
from .services.telegram_gateway_service import TelegramGatewayService
from .services.telegram_message_service import TelegramMessageService
from .services.telegram_settings_service import TelegramSettingsService


def _repository(name: str):
    return lambda: getattr(repositories(), name)


class AppServices:
    """The only production composition root for application services."""

    def __init__(self) -> None:
        transaction = transactional_repositories

        config_repo = _repository("config")
        editorial_profile_repo = _repository("editorial_profiles")
        runtime_lease_repo = _repository("runtime_leases")
        scraper_state_repo = _repository("scraper_state")
        scraper_command_repo = _repository("scraper_commands")
        delivery_operation_repo = _repository("delivery_operations")
        delivery_execution_repo = _repository("delivery_execution")
        review_repo = _repository("review")

        self.ai_provider_settings = AIProviderSettingsService(config_repo, transaction)
        self.ai_quality = AIQualityService(_repository("ai_quality"), self.ai_provider_settings)
        self.automation_settings = AutomationSettingsService(config_repo, transaction)
        self.delivery_settings = DeliverySettingsService(config_repo, transaction)
        self.system_settings = SystemSettingsService(config_repo)
        self.telegram_settings = TelegramSettingsService(config_repo, transaction)
        self.publications = PublicationService(_repository("publications"), transaction)
        self.editorial_profiles = EditorialProfileService(
            editorial_profile_repo, _repository("publications"), transaction
        )
        self.editorial_workbench = EditorialWorkbenchService(
            _repository("editorial_workbench"), transaction
        )
        self.event_intelligence = EventIntelligenceService(
            _repository("event_intelligence"), transaction
        )
        self.intelligence_catalog = IntelligenceCatalogService(
            _repository("intelligence_catalog"),
            _repository("event_intelligence"),
            transaction,
        )
        self.review_settings = ReviewSettingsService(config_repo, editorial_profile_repo, transaction)
        self.system_configuration = SystemConfigurationService(
            self.system_settings, self.automation_settings, self.delivery_settings, transaction
        )
        self.credentials = CredentialService(transaction)

        self.blacklist = BlacklistService(_repository("blacklist"))
        self.analyst_access = AnalystAccessService(_repository("api_keys"))
        self.analyst_data = AnalystDataService(
            self.analyst_access,
            _repository("event_intelligence"),
            _repository("intelligence_catalog"),
            _repository("market_intelligence"),
            _repository("tags"),
        )
        self.content = ContentService(
            _repository("news_admin"),
            _repository("content_queries"),
            _repository("event_queries"),
            _repository("archive_query"),
            _repository("review_admin"),
            config_repo,
        )
        self.content_lifecycle = ContentLifecycleService(
            review_repo, transaction
        )
        self.content_transitions = ContentTransitionService(transaction)
        self.public_content = PublicContentService(
            editorial_profile_repo,
            _repository("review_public"),
            _repository("daily_reports"),
            _repository("publications"),
            settings.PUBLIC_SITE_URL,
            settings.PUBLIC_LINKS,
        )

        self.rss_sources = RssSourceService(_repository("rss_sources"), transaction)
        site_scrapers = tuple(
            RegisteredScraper(
                name=definition.name,
                display_name=definition.display_name(),
                source_site=definition.source_site(),
                content_kind=definition.content_kind,
                default_limit=definition.default_limit,
                default_interval=definition.default_interval,
                source_type="site",
                transport_kind=getattr(definition.scraper_cls, "transport_kind", "browser"),
                build_scraper=definition.scraper_cls,
                authority_type="media",
                is_official=False,
            )
            for definition in scraper_catalog.definitions()
        )
        self.scraper_registry = ScraperRegistryService(
            self.rss_sources, site_scrapers, RssFeedScraper
        )
        self.source_operations = SourceOperationsService(
            _repository("source_operations"), self.scraper_registry, transaction, config_repo
        )
        self.market_intelligence = MarketIntelligenceService(
            _repository("market_intelligence"),
            _repository("intelligence_catalog"),
            _repository("event_intelligence"),
            MarketDataGateway(),
            transaction,
        )
        self.scraper_runtime_state = ScraperRuntimeStateService(
            config_repo, scraper_state_repo, self.scraper_registry
        )
        self.scraper_runs = ScraperRunService(
            _repository("news"),
            _repository("news_runtime"),
            scraper_state_repo,
            self.scraper_runtime_state,
            self.automation_settings,
        )
        self.operation_leases = OperationLeaseService(runtime_lease_repo)
        self.data_maintenance = DataMaintenanceService(
            self.automation_settings,
            config_repo,
            _repository("maintenance"),
            self.operation_leases,
        )
        self.scraper_schedule = ScraperScheduleService(
            scraper_command_repo,
            self.scraper_registry,
            self.scraper_runs,
            self.scraper_runtime_state,
            self.operation_leases,
            self.source_operations,
        )
        self.scraper_commands = ScraperCommandService(
            scraper_command_repo,
            self.scraper_runs,
            self.scraper_runtime_state,
            transaction,
            settings.APP_VERSION,
        )

        self.telegram_messages = TelegramMessageService(
            settings.PUBLIC_TELEGRAM_URL or settings.PUBLIC_SITE_URL
        )
        self.telegram_gateway = TelegramGatewayService(config_repo)
        self.publication_channel_gateway = PublicationChannelGateway(
            _repository("publications"), self.telegram_gateway
        )
        self.delivery_operations = DeliveryOperationService(
            delivery_operation_repo,
            delivery_execution_repo,
            self.publication_channel_gateway,
            transaction,
        )
        self.analyst_subscriptions = AnalystSubscriptionService(
            _repository("analyst_subscriptions"),
            _repository("publications"),
            _repository("event_intelligence"),
            _repository("intelligence_catalog"),
            _repository("tags"),
            self.delivery_operations,
            transaction,
        )
        self.digest_planner = DigestPlannerService()
        self.daily_reports = DailyReportService(
            editorial_profile_repo,
            _repository("review_delivery"),
            self.digest_planner,
            self.telegram_messages,
            transaction,
        )
        self.daily_delivery = DailyDeliveryService(
            config_repo,
            self.delivery_settings,
            delivery_operation_repo,
            delivery_execution_repo,
            self.daily_reports,
            self.delivery_operations,
        )
        self.automatic_entry_delivery = AutomaticEntryDeliveryService(
            editorial_profile_repo,
            _repository("push"),
            review_repo,
            self.telegram_gateway,
            self.telegram_messages,
            self.delivery_operations,
        )
        self.manual_entry_delivery = ManualEntryDeliveryService(
            _repository("review_delivery"),
            review_repo,
            delivery_operation_repo,
            self.telegram_messages,
            self.delivery_operations,
        )
        self.delivery_retry = DeliveryRetryService(
            delivery_operation_repo,
            self.delivery_operations,
            self.daily_delivery,
            self.manual_entry_delivery,
        )
        self.telegram_automation_delivery = TelegramAutomationDeliveryService(
            self.telegram_gateway,
            self.daily_delivery,
            self.automatic_entry_delivery,
        )
        self.publication_workflow = PublicationWorkflowService(
            _repository("editorial_workbench"),
            _repository("publications"),
            _repository("daily_reports"),
            _repository("review_delivery"),
            review_repo,
            _repository("push"),
            _repository("intelligence_catalog"),
            _repository("event_intelligence"),
            self.digest_planner,
            self.telegram_messages,
            self.delivery_operations,
            self.publication_channel_gateway,
            config_repo,
            transaction,
        )
        self.publication_workflow.alert_evaluator = self.intelligence_catalog.evaluate_alerts
        self.publication_workflow.classification_runner = self.intelligence_catalog.classify_recent
        self.publication_workflow.analyst_subscription_runner = self.analyst_subscriptions.deliver

        self.ai_pipeline = AIPipelineService(
            self.ai_provider_settings,
            self.automation_settings,
            editorial_profile_repo,
            _repository("event_queries"),
            review_repo,
            _repository("review_admin"),
            _repository("ai_quality"),
            transaction,
        )
        self.event_clustering = EventClusteringService(
            _repository("news_runtime"),
            self.automation_settings,
            self.content_transitions,
            build_event_clusterer,
        )
        self.pipeline = PipelineOrchestrator(
            self.operation_leases,
            self.content_transitions,
            self.ai_pipeline,
            self.event_clustering,
            self.scraper_runs,
            self.publication_workflow,
            self.automation_settings,
            _repository("processing"),
            editorial_profile_repo,
            self.source_operations,
            self.market_intelligence,
        )
        self.automation_runtime = AutomationRuntimeService(
            self.automation_settings,
            self.system_settings,
            self.scraper_schedule,
            self.pipeline,
            runtime_lease_repo,
            settings.APP_VERSION,
            self.data_maintenance,
        )
        self.runtime_health = RuntimeHealthService(database, runtime_lease_repo, settings.APP_VERSION)

    @staticmethod
    def auth() -> AuthService:
        return AuthService(repositories().config)


app_services = AppServices()
