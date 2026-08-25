from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import sqlite3
import tempfile
import threading
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

import backend.main as main_module
import backend.worker as worker_module
from shared.content_contract import delivery_key
from backend.app.composition import app_services
from backend.app.core.config import settings
from backend.app.core.exceptions import BusinessError, ValidationError
from backend.app.infrastructure.database import database, init_database
from backend.app.infrastructure.repositories import repositories
from backend.app.services.auth_service import AUTH_VERSION_KEY, AuthService
from backend.app.services.operation_lease_service import OperationLeaseService
from backend.app.services.pipeline_orchestrator import PipelineOrchestrator
from backend.app.services.automation_runtime_service import AutomationRuntimeService
from backend.app.services.ai_pipeline_service import AIPipelineService
from backend.app.infrastructure.sqlite.sqlite_migration_plan import (
    LEGACY_BASELINE_VERSION,
    INTELLIGENCE_FOUNDATION_VERSION,
    MIGRATION_STEPS,
    PERFORMANCE_SCHEMA_VERSION,
    SCHEMA_VERSION,
    WORKER_RUNTIME_VERSION,
)

content_service = app_services.content
delivery_operation_service = app_services.delivery_operations
editorial_profile_service = app_services.editorial_profiles
scraper_command_service = app_services.scraper_commands
scraper_run_service = app_services.scraper_runs
scraper_runtime_state_service = app_services.scraper_runtime_state
telegram_gateway_service = app_services.telegram_gateway
daily_delivery_service = app_services.daily_delivery
telegram_message_service = app_services.telegram_messages


class ReliabilityTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        tools_dir = Path(r"D:\Tools")
        tools_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir = tempfile.TemporaryDirectory(dir=tools_dir)
        self.original_db_path = database.db_path
        database.db_path = str(Path(self.temp_dir.name) / "reliability.db")
        init_database()

    async def asyncTearDown(self):
        database.db_path = self.original_db_path
        self.temp_dir.cleanup()

    async def test_database_constraints_and_user_rss_settings_survive_restart(self):
        conn = database.connect()
        try:
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO news_tags (news_id, tag_id) VALUES (999999, 999999)")
        finally:
            conn.close()

        repositories().rss_sources.execute(
            "UPDATE rss_sources SET enabled = 0, display_name = 'User label' WHERE slug = 'chainfeeds'"
        )
        init_database()
        source = repositories().rss_sources.get_source_by_slug("chainfeeds")
        self.assertEqual(source["enabled"], 0)
        self.assertEqual(source["display_name"], "User label")

    async def test_current_schema_startup_skips_the_migration_path_entirely(self):
        lock_path = Path(f"{database.db_path}.migration.lock")
        lock_existed_before = lock_path.exists()
        original_init_locked = database._init_db_locked
        try:
            database._init_db_locked = lambda: (_ for _ in ()).throw(
                AssertionError("同版本启动不应进入迁移写路径")
            )
            init_database()
        finally:
            database._init_db_locked = original_init_locked
        self.assertEqual(lock_path.exists(), lock_existed_before)

    async def test_export_stream_reads_all_rows_across_database_batches(self):
        conn = database.connect()
        try:
            conn.execute("BEGIN")
            conn.executemany(
                """
                INSERT INTO news (title, content, source_site, source_url, published_at, stage, type)
                VALUES (?, ?, 'ExportSource', ?, '2026-08-12 00:00:00', 'incoming', 'news')
                """,
                [(f"Export {index}", "body", f"https://example.test/export/{index}") for index in range(501)],
            )
            conn.commit()
        finally:
            conn.close()

        items = list(content_service.stream_export_content("incoming", None, None, None, None, "news", "id,title"))
        self.assertEqual(len(items), 501)
        self.assertTrue(all(set(item) == {"id", "title"} for item in items))

    async def test_unversioned_database_is_backed_up_before_migration(self):
        legacy_path = Path(self.temp_dir.name) / "legacy.db"
        conn = sqlite3.connect(legacy_path)
        conn.execute("CREATE TABLE legacy_marker (value TEXT)")
        conn.execute("INSERT INTO legacy_marker VALUES ('preserve me')")
        conn.commit()
        conn.close()

        database.db_path = str(legacy_path)
        init_database()

        backups = list((legacy_path.parent / "archive" / "database-backups").glob("legacy-before-unversioned-*.db"))
        self.assertEqual(len(backups), 1)
        backup_conn = sqlite3.connect(backups[0])
        try:
            self.assertEqual(backup_conn.execute("SELECT value FROM legacy_marker").fetchone()[0], "preserve me")
        finally:
            backup_conn.close()
        migrated = database.connect()
        try:
            version = migrated.execute("SELECT version FROM schema_migrations ORDER BY rowid DESC LIMIT 1").fetchone()[0]
            self.assertEqual(version, SCHEMA_VERSION)
        finally:
            migrated.close()

    async def test_legacy_push_logs_are_migrated_to_review_entry_semantics(self):
        conn = database.connect()
        try:
            conn.execute("DROP TABLE push_logs")
            conn.execute(
                """
                CREATE TABLE push_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    news_id INTEGER,
                    platform TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT,
                    pushed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "INSERT INTO push_logs (news_id, platform, status, message) VALUES (999, 'telegram', 'failed', 'legacy')"
            )
            conn.execute("DELETE FROM schema_migrations")
            conn.execute("INSERT INTO schema_migrations (version) VALUES ('2026.08.11.1')")
        finally:
            conn.close()

        init_database()
        migrated = database.connect()
        try:
            columns = {row["name"] for row in migrated.execute("PRAGMA table_info(push_logs)").fetchall()}
            self.assertIn("review_entry_id", columns)
            self.assertNotIn("news_id", columns)
            row = migrated.execute("SELECT review_entry_id, operation_key FROM push_logs").fetchone()
            self.assertIsNone(row["review_entry_id"])
            self.assertTrue(row["operation_key"].startswith("legacy:push:"))
            foreign_keys = migrated.execute("PRAGMA foreign_key_list(push_logs)").fetchall()
            self.assertTrue(any(item["table"] == "review_entries" for item in foreign_keys))
        finally:
            migrated.close()

    async def test_lifespan_fails_fast_and_preserves_original_runtime_exception(self):
        original_init = main_module.init_database
        original_ensure = main_module.app_services.scraper_runtime_state.ensure_runtime_initialized
        try:
            main_module.init_database = lambda: (_ for _ in ()).throw(RuntimeError("startup failure"))
            with self.assertRaisesRegex(RuntimeError, "startup failure"):
                async with main_module.lifespan(None):
                    self.fail("初始化失败后不应进入应用生命周期")

            main_module.init_database = lambda: None
            main_module.app_services.scraper_runtime_state.ensure_runtime_initialized = lambda: None
            with self.assertRaisesRegex(ValueError, "request failure"):
                async with main_module.lifespan(None):
                    raise ValueError("request failure")
        finally:
            main_module.init_database = original_init
            main_module.app_services.scraper_runtime_state.ensure_runtime_initialized = original_ensure

    async def test_health_readiness_separates_api_and_pipeline_dependencies(self):
        with TestClient(main_module.app) as client:
            self.assertEqual(client.get("/health/live").status_code, 200)
            api_ready = client.get("/health/ready")
            self.assertEqual(api_ready.status_code, 200)
            self.assertTrue(api_ready.json()["checks"]["database"]["foreign_keys"])

            not_ready = client.get("/health/pipeline")
            self.assertEqual(not_ready.status_code, 503)
            self.assertFalse(not_ready.json()["checks"]["worker"]["ready"])

            self.assertTrue(
                repositories().runtime_leases.acquire(
                    "worker",
                    "health-test-worker",
                    30,
                    owner_version=settings.APP_VERSION,
                    runtime_status="ready",
                )
            )
            ready = client.get("/health/pipeline")
            self.assertEqual(ready.status_code, 200)
            self.assertTrue(ready.json()["checks"]["database"]["foreign_keys"])
            self.assertEqual(ready.json()["checks"]["worker"]["instance_id"], "health-test-worker")

    async def test_scraper_failure_and_worker_recovery_are_truthful(self):
        class FailingScraper:
            site_name = "failing-source"
            max_items = 1

            async def run(self):
                raise RuntimeError("source layout changed")

        class Definition:
            @staticmethod
            def build_scraper():
                return FailingScraper()

        name = "test-failing-scraper"
        worker_id = "reliability-worker"
        original_require = scraper_runtime_state_service.require_scraper
        try:
            scraper_runtime_state_service.require_scraper = lambda requested_name: Definition()
            scraper_run_service.configure_worker(worker_id)
            run_id = uuid.uuid4().hex
            self.assertTrue(repositories().scraper_state.claim_run(name, run_id, worker_id))
            await scraper_run_service.run_scraper_task(name, 5, run_id)
        finally:
            scraper_runtime_state_service.require_scraper = original_require
        state = repositories().scraper_state.get_state(name)
        self.assertEqual(state["status"], "error")
        self.assertIn("source layout changed", state["last_error"])
        with self.assertRaisesRegex(RuntimeError, "source layout changed"):
            await scraper_run_service.wait_for_scrapers(timeout=1)

        command_id = repositories().scraper_commands.enqueue_command(name, "run", {"items": 5})
        repositories().scraper_commands.execute(
            """
            UPDATE scraper_runtime_commands
            SET status = 'processing', lease_expires_at = datetime('now', '-1 minute')
            WHERE id = ?
            """,
            (command_id,),
        )
        recovery = scraper_command_service.prepare_worker(worker_id)
        self.assertEqual(recovery["recovered_commands"], 1)
        command = repositories().scraper_commands.execute(
            "SELECT status FROM scraper_runtime_commands WHERE id = ?", (command_id,)
        ).fetchone()
        self.assertEqual(command["status"], "pending")

    async def test_scraper_stops_when_its_run_heartbeat_loses_ownership(self):
        class SlowScraper:
            site_name = "slow-source"
            max_items = 1

            async def run(self):
                await asyncio.sleep(30)
                return []

        class Definition:
            @staticmethod
            def build_scraper():
                return SlowScraper()

        async def heartbeat_failure(name, run_id, pending_logs):
            raise RuntimeError("run ownership lost")

        name = "test-heartbeat-loss"
        worker_id = "heartbeat-worker"
        original_require = scraper_runtime_state_service.require_scraper
        original_heartbeat = scraper_run_service._heartbeat_run
        try:
            scraper_runtime_state_service.require_scraper = lambda requested_name: Definition()
            scraper_run_service._heartbeat_run = heartbeat_failure
            scraper_run_service.configure_worker(worker_id)
            run_id = uuid.uuid4().hex
            self.assertTrue(repositories().scraper_state.claim_run(name, run_id, worker_id))
            await scraper_run_service.run_scraper_task(name, 1, run_id)
        finally:
            scraper_runtime_state_service.require_scraper = original_require
            scraper_run_service._heartbeat_run = original_heartbeat

        state = repositories().scraper_state.get_state(name)
        self.assertEqual(state["status"], "error")
        self.assertIn("run ownership lost", state["last_error"])
        with self.assertRaisesRegex(RuntimeError, "run ownership lost"):
            await scraper_run_service.wait_for_scrapers(timeout=1)

    async def test_worker_lease_allows_only_one_owner(self):
        repo = repositories().runtime_leases
        self.assertTrue(repo.acquire("worker", "worker-a", 30))
        self.assertFalse(repo.acquire("worker", "worker-b", 30))
        self.assertTrue(repo.release("worker", "worker-a"))
        self.assertTrue(repo.acquire("worker", "worker-b", 30))

    async def test_expired_owner_can_recover_lease_but_another_owner_cannot_take_it(self):
        repo = repositories().runtime_leases
        self.assertTrue(repo.acquire("lease-recovery", "owner-a", 30))
        repo.execute(
            "UPDATE runtime_leases SET lease_expires_at = datetime('now', '-1 second') WHERE name = ?",
            ("lease-recovery",),
        )
        self.assertTrue(repo.renew("lease-recovery", "owner-a", 30))
        self.assertFalse(repo.acquire("lease-recovery", "owner-b", 30))

    async def test_operation_heartbeat_survives_a_writer_lock_longer_than_ttl(self):
        service = OperationLeaseService(lambda: repositories().runtime_leases)
        async with service.hold("lease-lock-recovery", ttl_seconds=1) as lease_lost:
            writer = database.connect()
            try:
                writer.execute("BEGIN IMMEDIATE")
                writer.execute(
                    "INSERT OR REPLACE INTO system_config (key, value) VALUES ('lease.lock.test', 'held')"
                )
                await asyncio.sleep(1.25)
                self.assertFalse(lease_lost.is_set())
                writer.commit()
                await asyncio.sleep(0.75)
                self.assertFalse(lease_lost.is_set())
            finally:
                if writer.in_transaction:
                    writer.rollback()
                writer.close()

    async def test_pipeline_readiness_requires_matching_version_and_clean_status(self):
        repo = repositories().runtime_leases
        self.assertTrue(
            repo.acquire(
                "worker",
                "versioned-worker",
                30,
                owner_version="old-version",
                runtime_status="ready",
            )
        )
        ready, payload = app_services.runtime_health.pipeline_readiness()
        self.assertFalse(ready)
        self.assertFalse(payload["checks"]["worker"]["version_matches"])

        self.assertTrue(
            repo.renew(
                "worker",
                "versioned-worker",
                30,
                owner_version=settings.APP_VERSION,
                runtime_status="degraded",
                status_details="pipeline failed",
            )
        )
        ready, payload = app_services.runtime_health.pipeline_readiness()
        self.assertFalse(ready)
        self.assertEqual(payload["checks"]["worker"]["details"], "pipeline failed")

        self.assertTrue(
            repo.renew(
                "worker",
                "versioned-worker",
                30,
                owner_version=settings.APP_VERSION,
                runtime_status="ready",
            )
        )
        ready, _ = app_services.runtime_health.pipeline_readiness()
        self.assertTrue(ready)

    async def test_operation_lease_loss_cancels_work_and_fences_late_thread_commits(self):
        actual_repo = repositories().runtime_leases

        class LoseOnRenewRepository:
            def acquire(self, name, owner, ttl_seconds):
                return actual_repo.acquire(name, owner, ttl_seconds)

            def renew(self, name, owner, ttl_seconds):
                return False

            def release(self, name, owner):
                return actual_repo.release(name, owner)

            def get(self, name):
                return actual_repo.get(name)

        service = OperationLeaseService(lambda: LoseOnRenewRepository())
        allow_late_write = threading.Event()
        late_write_finished = threading.Event()
        late_write_errors = []

        def late_write():
            allow_late_write.wait(timeout=5)
            try:
                repositories().config.set_config("lease.fenced.write", "must-not-commit")
            except Exception as exc:
                late_write_errors.append(exc)
            finally:
                late_write_finished.set()

        late_task = None
        with self.assertRaisesRegex(BusinessError, "执行权已失效"):
            async with service.hold("lease-fencing-test", ttl_seconds=1):
                late_task = asyncio.create_task(asyncio.to_thread(late_write))
                await asyncio.sleep(5)

        allow_late_write.set()
        self.assertTrue(await asyncio.to_thread(late_write_finished.wait, 5))
        if late_task is not None:
            await late_task
        self.assertTrue(any(isinstance(exc, BusinessError) for exc in late_write_errors))
        self.assertIsNone(repositories().config.get_config("lease.fenced.write"))

    async def test_automation_cycle_drains_multiple_batches_and_reports_the_tail(self):
        calls = {"news": 0, "article": 0}
        outcomes = {
            "news": iter(({"remaining": 3, "enrichment_remaining": 0}, {"remaining": 0, "enrichment_remaining": 0})),
            "article": iter(({"remaining": 5, "enrichment_remaining": 0}, {"remaining": 4, "enrichment_remaining": 0})),
        }

        class Leases:
            @asynccontextmanager
            async def hold(self, name, ttl_seconds=120):
                yield asyncio.Event()

        class AI:
            async def run_content_review(self, hours, kind):
                calls[kind] += 1
                return next(outcomes[kind])

        class Clustering:
            async def auto_cluster_content(self, content_kind):
                return {"kind": content_kind}

        class Scrapers:
            async def wait_for_scrapers(self):
                return None

        class Delivery:
            async def run_cycle(self):
                return None

        class Settings:
            def get_runtime(self):
                return {"max_review_batches_per_cycle": 2}

            def get_window(self, kind):
                return {"filter_hours": 24, "ai_scoring_hours": 24}

        class Profiles:
            def list_profiles(self, kind, enabled_only=True):
                return [{"review_prompt": "review"}]

        class Processing:
            def log_processing(self, *args, **kwargs):
                return None

        orchestrator = PipelineOrchestrator(
            Leases(),
            type("Transitions", (), {"apply_blocklist": lambda self, hours, kind: {"kind": kind}})(),
            AI(),
            Clustering(),
            Scrapers(),
            Delivery(),
            Settings(),
            lambda: Processing(),
            lambda: Profiles(),
        )
        result = await orchestrator.run_automation_cycle()

        self.assertEqual(calls, {"news": 2, "article": 2})
        self.assertTrue(result["backlog_pending"])
        self.assertFalse(result["backlog_unknown"])
        self.assertEqual(result["remaining_by_kind"], {"article": 4})

    async def test_backlog_uses_short_retry_instead_of_the_hourly_schedule(self):
        class Settings:
            def get_runtime(self):
                return {"backlog_retry_seconds": 17}

        runtime = AutomationRuntimeService(Settings(), None, None, None, None, "test-version")
        self.assertEqual(runtime._seconds_after_pipeline({"backlog_pending": True}), 17)
        self.assertEqual(runtime._seconds_after_pipeline({"backlog_unknown": True}), 17)
        self.assertEqual(runtime._seconds_after_pipeline({"failures": [{"stage": "review"}]}), 17)

    async def test_blocklist_failure_skips_only_dependent_review_and_keeps_other_work(self):
        review_calls = []
        delivery_calls = []

        class Leases:
            @asynccontextmanager
            async def hold(self, name, ttl_seconds=120):
                yield asyncio.Event()

        class Transitions:
            def apply_blocklist(self, hours, kind):
                if kind == "news":
                    raise RuntimeError("broken news rule")
                return {"kind": kind}

        class AI:
            async def run_content_review(self, hours, kind):
                review_calls.append(kind)
                return {"remaining": 0, "enrichment_remaining": 0}

        class Clustering:
            async def auto_cluster_content(self, content_kind):
                return {"kind": content_kind}

        class Scrapers:
            async def wait_for_scrapers(self):
                return None

        class Delivery:
            async def run_cycle(self):
                delivery_calls.append(True)

        class Settings:
            def get_runtime(self):
                return {"max_review_batches_per_cycle": 1}

            def get_window(self, kind):
                return {"filter_hours": 24, "ai_scoring_hours": 24}

        class Profiles:
            def list_profiles(self, kind, enabled_only=True):
                return [{"review_prompt": "review"}]

        class Processing:
            def log_processing(self, *args, **kwargs):
                return None

        orchestrator = PipelineOrchestrator(
            Leases(), Transitions(), AI(), Clustering(), Scrapers(), Delivery(), Settings(),
            lambda: Processing(), lambda: Profiles(),
        )
        result = await orchestrator.run_automation_cycle()
        self.assertEqual(review_calls, ["article"])
        self.assertEqual(delivery_calls, [True])
        self.assertEqual(result["failures"][0]["stage"], "blocklist:news")
        self.assertEqual(result["skipped"], [{"stage": "review:news", "reason": "blocklist:news failed"}])
        self.assertTrue(result["backlog_unknown"])

    async def test_worker_validates_configuration_before_touching_database(self):
        original_validate = worker_module.settings.validate
        original_database_ready = worker_module.assert_database_ready
        database_touched = False

        def database_ready():
            nonlocal database_touched
            database_touched = True

        try:
            worker_module.settings.validate = lambda: (_ for _ in ()).throw(RuntimeError("invalid worker config"))
            worker_module.assert_database_ready = database_ready
            with self.assertRaisesRegex(RuntimeError, "invalid worker config"):
                await worker_module.main()
        finally:
            worker_module.settings.validate = original_validate
            worker_module.assert_database_ready = original_database_ready
        self.assertFalse(database_touched)

    async def test_ordered_migration_registry_has_one_contiguous_current_step(self):
        self.assertEqual(len(MIGRATION_STEPS), 4)
        self.assertEqual(MIGRATION_STEPS[0].from_version, LEGACY_BASELINE_VERSION)
        self.assertEqual(MIGRATION_STEPS[0].to_version, WORKER_RUNTIME_VERSION)
        self.assertEqual(MIGRATION_STEPS[1].from_version, WORKER_RUNTIME_VERSION)
        self.assertEqual(MIGRATION_STEPS[1].to_version, PERFORMANCE_SCHEMA_VERSION)
        self.assertEqual(MIGRATION_STEPS[2].from_version, PERFORMANCE_SCHEMA_VERSION)
        self.assertEqual(MIGRATION_STEPS[2].to_version, INTELLIGENCE_FOUNDATION_VERSION)
        self.assertEqual(MIGRATION_STEPS[3].from_version, INTELLIGENCE_FOUNDATION_VERSION)
        self.assertEqual(MIGRATION_STEPS[3].to_version, SCHEMA_VERSION)

        conn = database.connect()
        try:
            versions = [row[0] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY rowid")]
            columns = {row[1] for row in conn.execute("PRAGMA table_info(runtime_leases)")}
        finally:
            conn.close()
        self.assertEqual(versions, [SCHEMA_VERSION])
        self.assertTrue({"owner_version", "runtime_status", "status_details"} <= columns)

    async def test_baseline_database_runs_only_the_registered_next_migration(self):
        conn = database.connect()
        try:
            conn.execute("DROP TABLE runtime_leases")
            conn.execute(
                """
                CREATE TABLE runtime_leases (
                    name TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    lease_expires_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute("DELETE FROM schema_migrations")
            conn.execute("INSERT INTO schema_migrations(version) VALUES (?)", (LEGACY_BASELINE_VERSION,))
        finally:
            conn.close()

        init_database()
        conn = database.connect()
        try:
            versions = [row[0] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY rowid")]
            columns = {row[1] for row in conn.execute("PRAGMA table_info(runtime_leases)")}
        finally:
            conn.close()
        self.assertEqual(
            versions,
            [LEGACY_BASELINE_VERSION, WORKER_RUNTIME_VERSION, PERFORMANCE_SCHEMA_VERSION, INTELLIGENCE_FOUNDATION_VERSION, SCHEMA_VERSION],
        )
        self.assertTrue({"owner_version", "runtime_status", "status_details"} <= columns)

    async def test_unknown_intermediate_schema_version_is_rejected(self):
        conn = database.connect()
        try:
            conn.execute("DELETE FROM schema_migrations")
            conn.execute("INSERT INTO schema_migrations(version) VALUES ('2026.08.20.1')")
        finally:
            conn.close()
        with self.assertRaisesRegex(RuntimeError, "不在已登记的迁移链"):
            init_database()

    async def test_worker_runtime_database_migrates_to_performance_schema_and_reopens_cleanly(self):
        conn = database.connect()
        try:
            trigger_rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger' AND name LIKE 'public_revision_%'"
            ).fetchall()
            for row in trigger_rows:
                conn.execute(f"DROP TRIGGER {row['name']}")
            conn.execute("DROP TABLE public_content_revisions")
            for index_name in (
                "idx_events_kind_last_seen",
                "idx_review_claim_queue",
                "idx_enrichment_claim_queue",
                "idx_review_public_feed",
                "idx_review_admin_list",
            ):
                conn.execute(f"DROP INDEX IF EXISTS {index_name}")
            conn.execute("DROP TRIGGER review_entries_fts_update")
            conn.execute(
                """
                CREATE TRIGGER review_entries_fts_update AFTER UPDATE ON review_entries BEGIN
                    INSERT INTO review_entries_fts(
                        review_entries_fts, rowid, title, content, review_summary, enriched_summary
                    ) VALUES (
                        'delete', old.id, old.title, old.content, old.review_summary, old.enriched_summary
                    );
                    INSERT INTO review_entries_fts(rowid, title, content, review_summary, enriched_summary)
                    VALUES (new.id, new.title, new.content, new.review_summary, new.enriched_summary);
                END
                """
            )
            conn.execute("DELETE FROM schema_migrations")
            conn.execute("INSERT INTO schema_migrations(version) VALUES (?)", (WORKER_RUNTIME_VERSION,))
        finally:
            conn.close()

        init_database()
        init_database()

        conn = database.connect()
        try:
            versions = [row[0] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY rowid")]
            indexes = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index' AND name LIKE 'idx_%'"
                )
            }
            revision_table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'public_content_revisions'"
            ).fetchone()
            fts_trigger = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = 'review_entries_fts_update'"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(
            versions,
            [WORKER_RUNTIME_VERSION, PERFORMANCE_SCHEMA_VERSION, INTELLIGENCE_FOUNDATION_VERSION, SCHEMA_VERSION],
        )
        self.assertTrue(
            {
                "idx_events_kind_last_seen",
                "idx_review_claim_queue",
                "idx_enrichment_claim_queue",
                "idx_review_public_feed",
                "idx_review_admin_list",
            }
            <= indexes
        )
        self.assertIsNotNone(revision_table)
        self.assertIn("AFTER UPDATE OF title, content, review_summary, enriched_summary", fts_trigger)

    async def test_ai_claim_heartbeat_stops_a_batch_after_claim_loss(self):
        service = AIPipelineService(None, None, None, None, None, None, None, None)
        service.CLAIM_LEASE_SECONDS = 1
        with self.assertRaisesRegex(BusinessError, "领取权已失效"):
            async with service._keep_claim_alive(lambda token, seconds: 0, "lost-claim"):
                await asyncio.sleep(5)

    async def test_invalid_scraper_command_payload_is_failed_instead_of_wedged(self):
        command_id = repositories().scraper_commands.enqueue_command("techflow", "run", {"items": 3})
        repositories().scraper_commands.execute(
            "UPDATE scraper_runtime_commands SET payload = '{broken-json' WHERE id = ?",
            (command_id,),
        )

        self.assertIsNone(repositories().scraper_commands.claim_next_command("worker-test"))
        row = repositories().scraper_commands.execute(
            "SELECT status, result_message, claimed_by, lease_expires_at FROM scraper_runtime_commands WHERE id = ?",
            (command_id,),
        ).fetchone()
        self.assertEqual(row["status"], "failed")
        self.assertIn("Invalid command payload", row["result_message"])
        self.assertIsNone(row["claimed_by"])
        self.assertIsNone(row["lease_expires_at"])

    async def test_telegram_parts_are_bounded_and_delivery_is_resumable(self):
        entry = {
            "id": 1,
            "title": "Long message",
            "source_url": "https://example.test/item",
            "content_type": "news",
            "content": "&" * 7000,
        }
        parts = telegram_message_service.format_entry_parts(entry)
        self.assertTrue(parts)
        self.assertTrue(all(len(part) <= 4096 for part in parts))
        self.assertEqual(sum(part.count("&amp;") for part in parts), 7000)

        operation = delivery_operation_service.prepare(
            "test-delivery:resumable",
            "test",
            "news",
            ["part one", "part two", "part three"],
            [],
        )
        outcomes = iter(
            [
                {"status": "sent", "error": None, "remote_message_id": "1"},
                {"status": "unknown", "error": "timeout", "remote_message_id": None},
            ]
        )
        calls = []
        original_send = telegram_gateway_service.send_message_result

        async def uncertain_send(message, parse_mode="HTML"):
            calls.append(message)
            return next(outcomes)

        try:
            telegram_gateway_service.send_message_result = uncertain_send
            first = await delivery_operation_service.send(operation["operation_key"])
            self.assertEqual(first["status"], "needs_attention")

            async def successful_send(message, parse_mode="HTML"):
                calls.append(message)
                return {"status": "sent", "error": None, "remote_message_id": str(len(calls))}

            telegram_gateway_service.send_message_result = successful_send
            completed = await delivery_operation_service.retry_operation(operation["operation_key"])
            repeated = await delivery_operation_service.send(operation["operation_key"])
        finally:
            telegram_gateway_service.send_message_result = original_send
        self.assertEqual(completed["status"], "sent")
        self.assertEqual(repeated["status"], "sent")
        self.assertEqual(calls, ["part one", "part two", "part two", "part three"])

    async def test_empty_daily_delivery_does_not_consume_the_date(self):
        config = repositories().config
        config.set_config(delivery_key("news", "time"), "00:00")
        result = await daily_delivery_service.send_news()
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["message"], "No content found")
        self.assertIsNone(config.get_config(delivery_key("news", "last_date")))

    async def test_auth_tokens_are_invalidated_and_database_password_is_hashed(self):
        original_username = settings.ADMIN_USERNAME
        original_password = settings.ADMIN_PASSWORD
        try:
            settings.ADMIN_USERNAME = ""
            settings.ADMIN_PASSWORD = ""
            config = repositories().config
            config.set_config("admin_username", "admin")
            config.set_config("admin_password", "temporary-password")
            auth = AuthService(config)
            self.assertTrue(auth.migrate_database_password())
            self.assertTrue(config.get_config("admin_password").startswith("pbkdf2_sha256$"))
            self.assertTrue(auth.authenticate_user("admin", "temporary-password"))
            token = auth.create_access_token({"sub": "admin"})
            self.assertEqual(auth.verify_token(token), "admin")
            config.set_config(AUTH_VERSION_KEY, "2")
            self.assertIsNone(auth.verify_token(token))
        finally:
            settings.ADMIN_USERNAME = original_username
            settings.ADMIN_PASSWORD = original_password

    async def test_default_profile_is_explicit_and_cannot_be_accidentally_removed(self):
        default_profile = repositories().editorial_profiles.get_default("news")
        self.assertEqual(default_profile["slug"], "daily-briefs")
        with self.assertRaises(ValidationError):
            editorial_profile_service.save_profile({**default_profile, "is_default": False})

        replacement = editorial_profile_service.save_profile(
            {
                "slug": "replacement-briefs",
                "name": "Replacement",
                "content_type": "news",
                "review_prompt": "Keep verified items",
                "enrichment_prompt": "",
                "min_score": 5,
                "max_items": 12,
                "max_per_category": 4,
                "max_per_source": 4,
                "enabled": True,
                "is_default": True,
            }
        )
        self.assertTrue(replacement["is_default"])
        self.assertEqual(repositories().editorial_profiles.get_default("news")["slug"], "replacement-briefs")


if __name__ == "__main__":
    unittest.main()
