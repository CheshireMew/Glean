from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, call, patch
import asyncio

from backend.app.composition import app_services
from backend.app.core.config import settings
from backend.app.infrastructure.event_clustering import EventCluster, EventMember, build_event_clusterer
from backend.app.infrastructure.database import database
from backend.app.infrastructure.repositories import repositories
from backend.app.infrastructure.sqlite.sqlite_migration_plan import WORKER_RUNTIME_VERSION
from backend.cli.app import main as cli_main
from backend.cli.errors import (
    CLIConflictError,
    CLIIncompleteError,
    CLINotFoundError,
    CLITimeoutError,
    CLIUnavailableError,
    CLIUsageError,
)
from backend.cli.models import CommandSpec
from backend.cli.registry import load_command_specs


class CLITest(unittest.TestCase):
    def setUp(self):
        tools_dir = Path(r"D:\Tools")
        tools_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir = tempfile.TemporaryDirectory(dir=tools_dir)
        self.original_db_path = database.db_path
        self.db_path = Path(self.temp_dir.name) / "glean-cli.db"
        database.db_path = str(self.db_path)

    def tearDown(self):
        database.db_path = self.original_db_path
        self.temp_dir.cleanup()

    @staticmethod
    def _run(*args: str, stdin: str | None = None):
        stdout = io.StringIO()
        stderr = io.StringIO()
        input_stream = io.StringIO(stdin) if stdin is not None else io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr), patch("sys.stdin", input_stream):
            code = cli_main(list(args))
        return code, json.loads(stdout.getvalue()), stderr.getvalue()

    def _init(self):
        code, payload, _ = self._run("system", "init")
        self.assertEqual(code, 0, payload)
        self.assertTrue(self.db_path.exists())

    def _seed_event(self, title: str, suffix: str, content_kind: str = "news") -> tuple[int, int, int]:
        news_id = repositories().news.insert_news(
            {
                "title": title,
                "content": f"{title} body",
                "source_site": "CLI Test",
                "url": f"https://example.test/{suffix}",
                "published_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "type": content_kind,
            }
        )
        row = dict(
            repositories().news.execute("SELECT * FROM news WHERE id = ?", (news_id,)).fetchone()
        )
        cluster = EventCluster(
            primary=row,
            members=[EventMember(item=row, similarity=1.0)],
            event_key=f"cli:{suffix}",
        )
        app_services.content_transitions.persist_event_clusters(
            [cluster], build_event_clusterer(0.5), content_kind, 24
        )
        event_id = int(repositories().events.get_event_id_for_news(news_id))
        archive_id = int(
            repositories().archive_query.execute(
                "SELECT id FROM archive_entries WHERE event_id = ?", (event_id,)
            ).fetchone()["id"]
        )
        return int(news_id), event_id, archive_id

    @staticmethod
    def _run_probe(exc: BaseException):
        def failing_handler(ctx, args, payload):
            raise exc

        spec = CommandSpec(
            "probe",
            ("probe",),
            "probe error mapping",
            failing_handler,
            database_mode="none",
        )
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("backend.cli.app.load_command_specs", return_value=[spec]), redirect_stdout(
            stdout
        ), redirect_stderr(stderr):
            code = cli_main(["probe"])
        return code, json.loads(stdout.getvalue()), stderr.getvalue()

    def test_version_capabilities_and_status_do_not_create_database(self):
        code, version, _ = self._run("version")
        self.assertEqual(code, 0)
        self.assertTrue(version["success"])
        self.assertFalse(self.db_path.exists())

        code, capabilities, _ = self._run("capabilities")
        self.assertEqual(code, 0)
        commands = capabilities["data"]["commands"]
        self.assertEqual(len(commands), len({item["id"] for item in commands}))
        self.assertIn("pipeline.cycle", {item["id"] for item in commands})
        self.assertFalse(self.db_path.exists())

        code, status, _ = self._run("system", "status")
        self.assertEqual(code, 5)
        self.assertFalse(status["data"]["database"]["exists"])
        self.assertFalse(self.db_path.exists())

    def test_init_then_read_and_update_configuration_from_stdin(self):
        self._init()
        code, status, _ = self._run("system", "status")
        self.assertEqual(code, 0, status)
        self.assertTrue(status["data"]["database"]["ready"])
        self.assertFalse(status["data"]["pipeline"]["ready"])

        code, overview, _ = self._run("content", "overview", "--kind", "news")
        self.assertEqual(code, 0, overview)
        self.assertEqual(overview["data"]["incoming"], 0)

        code, changed, _ = self._run(
            "config",
            "timezone",
            "set",
            "--input",
            "-",
            stdin=json.dumps({"timezone": "UTC"}),
        )
        self.assertEqual(code, 0, changed)
        code, current, _ = self._run("config", "timezone", "get")
        self.assertEqual(code, 0)
        self.assertEqual(current["data"]["timezone"], "UTC")

    def test_outdated_database_is_not_migrated_by_ordinary_commands(self):
        self._init()
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("DELETE FROM schema_migrations")
            connection.execute(
                "INSERT INTO schema_migrations(version) VALUES (?)", (WORKER_RUNTIME_VERSION,)
            )
            connection.commit()

        code, rejected, _ = self._run("content", "overview")
        self.assertEqual(code, 5, rejected)
        with sqlite3.connect(self.db_path) as connection:
            version = connection.execute(
                "SELECT version FROM schema_migrations ORDER BY applied_at DESC LIMIT 1"
            ).fetchone()[0]
        self.assertEqual(version, WORKER_RUNTIME_VERSION)

        code, initialized, _ = self._run("system", "init")
        self.assertEqual(code, 0, initialized)
        self.assertFalse(initialized["data"]["created"])
        backups = list((self.db_path.parent / "archive" / "database-backups").glob("*.db"))
        self.assertEqual(len(backups), 1)
        code, overview, _ = self._run("content", "overview")
        self.assertEqual(code, 0, overview)

    def test_json_validation_and_confirmation_fail_before_mutation(self):
        self._init()
        entry_id = repositories().news.insert_news(
            {
                "title": "CLI confirmation",
                "content": "body",
                "source_site": "CLI Test",
                "url": "https://example.test/cli-confirmation",
                "published_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "type": "news",
            }
        )
        code, rejected, _ = self._run(
            "content", "delete", "--scope", "incoming", "--id", str(entry_id)
        )
        self.assertEqual(code, 2)
        self.assertEqual(rejected["error"]["type"], "UsageError")
        self.assertIsNotNone(repositories().news.execute("SELECT id FROM news WHERE id = ?", (entry_id,)).fetchone())

        code, invalid, _ = self._run(
            "config", "timezone", "set", "--input", "-", stdin="[]"
        )
        self.assertEqual(code, 2)
        self.assertEqual(invalid["error"]["type"], "UsageError")

    def test_streaming_export_reports_file_integrity(self):
        self._init()
        repositories().news.insert_news(
            {
                "title": "CLI export",
                "content": "export body",
                "source_site": "CLI Test",
                "url": "https://example.test/cli-export",
                "published_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "type": "news",
            }
        )
        output = Path(self.temp_dir.name) / "export.json"
        code, exported, _ = self._run(
            "content",
            "export",
            "--scope",
            "incoming",
            "--output",
            str(output),
        )
        self.assertEqual(code, 0, exported)
        self.assertEqual(exported["data"]["count"], 1)
        self.assertEqual(len(exported["data"]["sha256"]), 64)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))[0]["title"], "CLI export")

        code, conflict, _ = self._run(
            "content",
            "export",
            "--scope",
            "incoming",
            "--output",
            str(output),
        )
        self.assertEqual(code, 4)
        self.assertEqual(conflict["error"]["type"], "ConflictError")

    def test_worker_requirement_maps_to_unavailable_exit_code(self):
        self._init()
        scraper_name = load_command_specs()
        self.assertTrue(scraper_name)
        from backend.app.composition import app_services

        name = app_services.scraper_registry.names()[0]
        code, result, _ = self._run("scraper", "run", name, "--items", "1")
        self.assertEqual(code, 5)
        self.assertEqual(result["error"]["type"], "ServiceUnavailableError")

    def test_business_prints_are_isolated_from_json_stdout(self):
        def noisy_handler(ctx, args, payload):
            print("business progress")
            return {"ok": True}

        spec = CommandSpec(
            "noisy",
            ("noisy",),
            "test noisy output",
            noisy_handler,
            database_mode="none",
        )
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("backend.cli.app.load_command_specs", return_value=[spec]), redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli_main(["noisy"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["data"], {"ok": True})
        self.assertIn("business progress", stderr.getvalue())

    def test_registry_import_does_not_load_optional_runtimes(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import json,sys; from backend.cli.registry import load_command_specs; "
                    "specs=load_command_specs(); print(json.dumps({"
                    "'count': len(specs), 'openai': 'openai' in sys.modules, "
                    "'playwright': any(n.startswith('playwright') for n in sys.modules)}))"
                ),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        metrics = json.loads(result.stdout.strip())
        self.assertGreater(metrics["count"], 50)
        self.assertFalse(metrics["openai"])
        self.assertFalse(metrics["playwright"])

    def test_capabilities_publish_specific_input_and_output_schemas(self):
        specs = load_command_specs()
        self.assertEqual(len(specs), 128)
        self.assertTrue(all(spec.help.strip() for spec in specs))
        self.assertTrue(all(spec.output_schema for spec in specs))
        for spec in specs:
            schema = spec.output_schema
            self.assertNotEqual(schema, {"type": "object", "additionalProperties": True})
            if schema.get("type") == "object":
                self.assertTrue(schema.get("properties"), spec.command_id)

        code, version, _ = self._run("capabilities", "version")
        self.assertEqual(code, 0, version)
        output_schema = version["data"]["commands"][0]["output_schema"]
        self.assertEqual(output_schema["required"], ["version"])

        code, config, _ = self._run("capabilities", "config.timezone.set")
        self.assertEqual(code, 0, config)
        command = config["data"]["commands"][0]
        self.assertIn("timezone", command["input_schema"]["properties"])
        self.assertEqual(command["output_schema"], {"type": "null"})

        protected = {spec.command_id for spec in specs if spec.requires_yes}
        self.assertEqual(
            protected,
            {
                "system.maintenance",
                "system.credentials",
                "content.delete",
                "content.restore",
                "content.clear-decisions",
                "pipeline.cycle",
                "blocklist.remove",
                "delivery.daily",
                "delivery.send",
                "delivery.retry",
                "delivery.test",
                "config.telegram.test",
                "rss.delete",
                "analyst-key.delete",
                "channel.test",
                "draft.publish",
                "draft.publish-due",
                "correction.publish",
                "alert.deliver",
                "ai-quality.evaluate",
                "analyst-subscription.deliver",
            },
        )

    def test_every_documented_exit_code_uses_one_json_envelope(self):
        cases = (
            (CLIUsageError("bad input"), 2, "UsageError"),
            (CLINotFoundError("missing"), 3, "NotFoundError"),
            (CLIConflictError("conflict"), 4, "ConflictError"),
            (CLIUnavailableError("unavailable"), 5, "ServiceUnavailableError"),
            (CLIIncompleteError("incomplete"), 6, "IncompleteOperation"),
            (CLITimeoutError("timeout"), 124, "TimeoutError"),
            (RuntimeError("unexpected"), 1, "RuntimeError"),
            (KeyboardInterrupt(), 130, "InterruptedError"),
        )
        for exc, expected_code, expected_type in cases:
            with self.subTest(exit_code=expected_code):
                code, payload, _ = self._run_probe(exc)
                self.assertEqual(code, expected_code, payload)
                self.assertFalse(payload["success"])
                self.assertEqual(payload["error"]["type"], expected_type)
                self.assertEqual(payload["command"], "probe")

    def test_global_output_and_debug_options(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli_main(["--format", "text", "version"])
        self.assertEqual(code, 0)
        self.assertTrue(stdout.getvalue().startswith("成功:"))

        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
            code = cli_main(["--pretty", "version"])
        self.assertEqual(code, 0)
        self.assertGreater(stdout.getvalue().count("\n"), 5)
        self.assertTrue(json.loads(stdout.getvalue())["success"])

        def broken_handler(ctx, args, payload):
            raise RuntimeError("debug traceback check")

        spec = CommandSpec(
            "broken", ("broken",), "debug test", broken_handler, database_mode="none"
        )
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("backend.cli.app.load_command_specs", return_value=[spec]), redirect_stdout(
            stdout
        ), redirect_stderr(stderr):
            code = cli_main(["--debug", "broken"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(stdout.getvalue())["error"]["type"], "RuntimeError")
        self.assertIn("Traceback", stderr.getvalue())
        self.assertIn("debug traceback check", stderr.getvalue())

    def test_content_delete_blocklist_and_restore_success_paths(self):
        self._init()
        incoming_id = repositories().news.insert_news(
            {
                "title": "CLI delete success",
                "content": "body",
                "source_site": "CLI Test",
                "url": "https://example.test/cli-delete-success",
                "published_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "type": "news",
            }
        )
        code, deleted, _ = self._run(
            "content", "delete", "--scope", "incoming", "--id", str(incoming_id), "--yes"
        )
        self.assertEqual(code, 0, deleted)
        self.assertIsNone(
            repositories().news.execute(
                "SELECT id FROM news WHERE id = ?", (incoming_id,)
            ).fetchone()
        )

        keyword = "CLI恢复验收"
        code, added, _ = self._run("blocklist", "add", keyword, "--kind", "news")
        self.assertEqual(code, 0, added)
        _, event_id, archive_id = self._seed_event(f"{keyword}：应被拦截", "cli-restore")
        code, applied, _ = self._run(
            "pipeline", "blocklist-apply", "--hours", "24", "--kind", "news"
        )
        self.assertEqual(code, 0, applied)
        self.assertEqual(
            repositories().archive_query.get_entry(archive_id)["archive_status"], "blocked"
        )

        code, restored, _ = self._run(
            "content", "restore", "--scope", "blocked", "--id", str(archive_id), "--yes"
        )
        self.assertEqual(code, 0, restored)
        pending = repositories().review.execute(
            "SELECT COUNT(*) AS total FROM review_entries WHERE event_id = ? AND review_status = 'pending'",
            (event_id,),
        ).fetchone()["total"]
        self.assertGreaterEqual(pending, 1)

        code, listed, _ = self._run("blocklist", "list", "--kind", "news")
        self.assertEqual(code, 0, listed)
        entry = next(item for item in listed["data"]["keywords"] if item["keyword"] == keyword)
        code, removed, _ = self._run("blocklist", "remove", str(entry["id"]), "--yes")
        self.assertEqual(code, 0, removed)

    def test_profile_rss_and_analyst_key_management(self):
        self._init()
        profile = {
            "slug": "cli-audit-profile",
            "name": "CLI Audit Profile",
            "content_type": "news",
            "review_prompt": "Keep relevant AI news",
            "enabled": True,
            "is_default": False,
        }
        code, mismatch, _ = self._run(
            "profile", "save", "different-slug", "--input", "-", stdin=json.dumps(profile)
        )
        self.assertEqual(code, 2, mismatch)
        code, saved, _ = self._run(
            "profile", "save", profile["slug"], "--input", "-", stdin=json.dumps(profile)
        )
        self.assertEqual(code, 0, saved)
        self.assertEqual(saved["data"]["slug"], profile["slug"])
        code, profiles, _ = self._run("profile", "list", "--kind", "news")
        self.assertEqual(code, 0, profiles)
        self.assertIn(profile["slug"], {item["slug"] for item in profiles["data"]["profiles"]})

        rss = {
            "slug": "cli-audit-feed",
            "display_name": "CLI Audit Feed",
            "feed_url": "https://example.test/feed.xml",
            "site_url": "https://example.test/",
            "content_kind": "article",
            "enabled": True,
        }
        code, created, _ = self._run(
            "rss", "create", "--input", "-", stdin=json.dumps(rss)
        )
        self.assertEqual(code, 0, created)
        rss_id = created["data"]["id"]
        rss["display_name"] = "CLI Audit Feed Updated"
        code, updated, _ = self._run(
            "rss", "update", str(rss_id), "--input", "-", stdin=json.dumps(rss)
        )
        self.assertEqual(code, 0, updated)
        self.assertEqual(updated["data"]["display_name"], rss["display_name"])
        code, feeds, _ = self._run("rss", "list")
        self.assertEqual(code, 0, feeds)
        self.assertIn(rss_id, {item["id"] for item in feeds["data"]["sources"]})
        code, removed, _ = self._run("rss", "delete", str(rss_id), "--yes")
        self.assertEqual(code, 0, removed)

        operation = "analyst-key"
        code, created_key, _ = self._run(operation, "create", "--name", "CLI Audit")
        self.assertEqual(code, 0, created_key)
        key_id = created_key["data"]["id"]
        plaintext = created_key["data"]["api_key"]
        self.assertTrue(plaintext.startswith("analyst_"))
        code, keys, _ = self._run(operation, "list")
        self.assertEqual(code, 0, keys)
        listed_key = next(item for item in keys["data"]["items"] if item["id"] == key_id)
        self.assertNotIn("api_key", listed_key)
        code, disabled, _ = self._run(operation, "disable", str(key_id))
        self.assertEqual(code, 0, disabled)
        code, enabled, _ = self._run(operation, "enable", str(key_id))
        self.assertEqual(code, 0, enabled)
        code, deleted_key, _ = self._run(operation, "delete", str(key_id), "--yes")
        self.assertEqual(code, 0, deleted_key)

    def test_ai_and_telegram_queries_mask_and_preserve_secrets(self):
        self._init()
        telegram = {"bot_token": "telegram-secret", "chat_id": "chat-1", "enabled": True}
        code, saved, _ = self._run(
            "config", "telegram", "set", "--input", "-", stdin=json.dumps(telegram)
        )
        self.assertEqual(code, 0, saved)
        code, public, _ = self._run("config", "telegram", "get")
        self.assertEqual(code, 0, public)
        self.assertEqual(public["data"]["bot_token"], "••••••••")
        self.assertNotIn("telegram-secret", json.dumps(public))
        telegram["bot_token"] = "••••••••"
        telegram["chat_id"] = "chat-2"
        code, retained, _ = self._run(
            "config", "telegram", "set", "--input", "-", stdin=json.dumps(telegram)
        )
        self.assertEqual(code, 0, retained)
        self.assertEqual(
            app_services.telegram_settings._config_repository().get_config(
                "integration.telegram.bot_token"
            ),
            "telegram-secret",
        )

        ai = {
            "providers": [
                {
                    "name": "primary",
                    "api_key": "ai-secret",
                    "base_url": "https://example.test/v1",
                    "model": "fake-model",
                }
            ],
            "analysis_concurrency": 2,
            "enrichment_concurrency": 1,
            "throttle_seconds": 0,
        }
        code, saved, _ = self._run("config", "ai", "set", "--input", "-", stdin=json.dumps(ai))
        self.assertEqual(code, 0, saved)
        code, public, _ = self._run("config", "ai", "get")
        self.assertEqual(code, 0, public)
        self.assertEqual(public["data"]["providers"][0]["api_key"], "••••••••")
        self.assertNotIn("ai-secret", json.dumps(public))
        ai["providers"][0]["api_key"] = "••••••••"
        code, retained, _ = self._run(
            "config", "ai", "set", "--input", "-", stdin=json.dumps(ai)
        )
        self.assertEqual(code, 0, retained)
        private = app_services.ai_provider_settings.get_config(include_secrets=True)
        self.assertEqual(private["providers"][0]["api_key"], "ai-secret")

    def test_external_checks_and_delivery_are_isolated_with_substitutes(self):
        self._init()
        telegram = {"bot_token": "test-token", "chat_id": "test-chat", "enabled": False}
        with patch.object(
            app_services.telegram_gateway,
            "send_test_message",
            new=AsyncMock(return_value={"status": "success", "message": "telegram ok"}),
        ) as send_test:
            code, tested, _ = self._run(
                "config",
                "telegram",
                "test",
                "--input",
                "-",
                "--yes",
                stdin=json.dumps(telegram),
            )
        self.assertEqual(code, 0, tested)
        send_test.assert_awaited_once()

        ai = {
            "providers": [
                {
                    "name": "fake",
                    "api_key": "test-key",
                    "base_url": "https://example.test/v1",
                    "model": "fake-model",
                }
            ]
        }
        with patch.object(
            app_services.ai_pipeline,
            "test_ai_connection",
            new=AsyncMock(return_value={"status": "success", "message": "ai ok"}),
        ) as test_ai:
            code, tested, _ = self._run(
                "config", "ai", "test", "--input", "-", stdin=json.dumps(ai)
            )
        self.assertEqual(code, 0, tested)
        test_ai.assert_awaited_once()

        operation_key = "manual:cli-idempotency-check"
        request = {"entries": [{"scope": "selected", "id": 1}], "operation_key": operation_key}
        sent_result = {
            "operation_key": operation_key,
            "status": "sent",
            "parts": 1,
            "sent_parts": 1,
            "last_error": None,
            "needs_attention": False,
        }
        with patch.object(
            app_services.manual_entry_delivery,
            "send",
            new=AsyncMock(return_value=sent_result),
        ) as send:
            for _ in range(2):
                code, delivered, _ = self._run(
                    "delivery", "send", "--input", "-", "--yes", stdin=json.dumps(request)
                )
                self.assertEqual(code, 0, delivered)
        expected_entries = [{"scope": "selected", "id": 1}]
        self.assertEqual(
            send.await_args_list,
            [call(expected_entries, operation_key), call(expected_entries, operation_key)],
        )

        attention = {**sent_result, "status": "needs_attention", "needs_attention": True}
        with patch.object(
            app_services.manual_entry_delivery,
            "send",
            new=AsyncMock(return_value=attention),
        ):
            code, incomplete, _ = self._run(
                "delivery", "send", "--input", "-", "--yes", stdin=json.dumps(request)
            )
        self.assertEqual(code, 6, incomplete)
        self.assertEqual(incomplete["data"]["status"], "needs_attention")

    def test_worker_preflight_wait_timeout_and_pipeline_lease_conflict(self):
        self._init()
        name = app_services.scraper_registry.names()[0]
        app_services.scraper_runtime_state.set_scraper_state(name, {"status": "running"})
        code, stopped, _ = self._run("scraper", "stop", name)
        self.assertEqual(code, 5, stopped)
        self.assertFalse(
            repositories().scraper_commands.has_pending_command(name, "stop")
        )

        self.assertTrue(
            repositories().runtime_leases.acquire(
                "worker",
                "cli-test-worker",
                30,
                owner_version=settings.APP_VERSION,
                runtime_status="ready",
            )
        )
        command_id = repositories().scraper_commands.enqueue_command(
            name, "run", {"items": 1}
        )
        code, timed_out, _ = self._run(
            "scraper", "wait", str(command_id), "--timeout", "1"
        )
        self.assertEqual(code, 124, timed_out)
        self.assertEqual(timed_out["error"]["type"], "TimeoutError")

        self.assertTrue(
            repositories().runtime_leases.acquire(
                "content-pipeline", "held-by-cli-test", 300
            )
        )
        code, cycle, _ = self._run("pipeline", "cycle", "--yes")
        self.assertEqual(code, 4, cycle)
        code, maintenance, _ = self._run(
            "system", "maintenance", "--force", "--yes"
        )
        self.assertEqual(code, 4, maintenance)

    def test_scraper_wait_does_not_finish_when_only_the_queue_command_is_complete(self):
        from backend.cli.commands import operations

        class FakeCommands:
            @staticmethod
            def get_command(command_id):
                return {
                    "id": command_id,
                    "scraper_name": "fake-scraper",
                    "status": "completed",
                }

        class FakeRuntime:
            def __init__(self):
                self.states = iter(({"status": "running"}, {"status": "idle"}))

            def get_scraper_state(self, name):
                return next(self.states)

        class FakeServices:
            scraper_commands = FakeCommands()
            scraper_runtime_state = FakeRuntime()

        class FakeContext:
            services = FakeServices()

        sleep = AsyncMock()
        with patch.object(operations.asyncio, "sleep", new=sleep):
            result = asyncio.run(operations._wait_for_scraper(FakeContext(), 7, 5))
        self.assertEqual(result["state"]["status"], "idle")
        sleep.assert_awaited_once_with(1)

    @unittest.skipUnless(sys.platform == "win32", "PowerShell wrapper is Windows-only")
    def test_powershell_wrapper_returns_json_and_exit_code(self):
        root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(root / "glean.ps1"),
                "version",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["success"])

        invalid = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(root / "glean.ps1"),
                "not-a-command",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(invalid.returncode, 2, invalid.stderr)
        self.assertEqual(json.loads(invalid.stdout)["error"]["type"], "UsageError")

        wrapper = (root / "glean.ps1").read_text(encoding="utf-8-sig")
        self.assertIn(r"D:\Tools\Python310\python.exe", wrapper)
        self.assertIn("@args", wrapper)
        self.assertIn("exit $LASTEXITCODE", wrapper)

    def test_python_module_entrypoint_runs_in_a_clean_process(self):
        root = Path(__file__).resolve().parents[2]
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "cp1252"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "backend.cli",
                "--env",
                "test",
                "version",
            ],
            cwd=root,
            capture_output=True,
            encoding="utf-8",
            env=env,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["meta"]["environment"], "test")
        self.assertEqual(payload["data"]["version"], payload["meta"]["app_version"])


class CLIArchitectureTest(unittest.TestCase):
    def test_command_registry_has_handlers_and_stable_unique_ids(self):
        specs = load_command_specs()
        self.assertEqual(len(specs), len({spec.command_id for spec in specs}))
        self.assertEqual(len(specs), len({spec.path for spec in specs}))
        self.assertTrue(all(callable(spec.handler) for spec in specs))

    def test_command_handlers_do_not_import_repository_implementations(self):
        commands = Path(__file__).resolve().parents[1] / "cli" / "commands"
        source = "\n".join(path.read_text(encoding="utf-8") for path in commands.glob("*.py"))
        self.assertNotIn("repository_impl", source)
        self.assertNotIn("infrastructure.repositories", source)
        self.assertNotIn("repositories()", source)


if __name__ == "__main__":
    unittest.main()
