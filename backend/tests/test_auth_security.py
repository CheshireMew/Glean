import concurrent.futures
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import jwt
from fastapi.testclient import TestClient

from backend.main import app
from backend.app.composition import app_services
from backend.app.core.config import settings
from backend.app.core.exceptions import APIException, ConfigurationError
from backend.app.infrastructure.database import database
from backend.app.infrastructure.repositories import repositories
from backend.app.services.auth_service import AuthService
from backend.reset_admin import reset_account


class AuthSecurityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Keep audit fixtures on D:, without deleting user files as part of this check.
        cls.fixture_dir = Path(tempfile.mkdtemp(prefix="ainews-auth-check-", dir=r"D:\Tools"))

    def setUp(self):
        self.old_path = database.db_path
        database.db_path = str(self.fixture_dir / f"{self._testMethodName}.db")
        self.settings_patch = patch.multiple(settings, JWT_SECRET_KEY="", ADMIN_USERNAME="", ADMIN_PASSWORD="")
        self.settings_patch.start()
        self.password = "Local-review!123456"
        reset_account("admin", self.password)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        database.db_path = self.old_path
        self.settings_patch.stop()

    def login(self, username="admin", password=None):
        return self.client.post("/api/login", data={"username": username, "password": self.password if password is None else password})

    def token(self):
        response = self.login()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        return response.json()["data"]["access_token"]

    def headers(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_logout_revokes_only_current_session_and_survives_new_service(self):
        first, second = self.token(), self.token()
        self.assertEqual(self.client.post("/api/logout", headers=self.headers(first)).status_code, 200)
        self.assertEqual(self.client.get("/api/session", headers=self.headers(first)).status_code, 401)
        self.assertEqual(self.client.get("/api/session", headers=self.headers(second)).status_code, 200)
        self.assertIsNone(app_services.auth().verify_token(first))
        self.assertEqual(app_services.auth().verify_token(second), "admin")

    def test_password_change_revokes_all_and_does_not_revert_to_env(self):
        first, second = self.token(), self.token()
        with patch.multiple(settings, ADMIN_USERNAME="old-env-admin", ADMIN_PASSWORD="old-env-password"):
            changed = self.client.post("/api/system/credentials", headers=self.headers(first), json={
                "current_password": self.password, "new_username": "  管理员甲  ", "new_password": "新密码-安全翻译系统-2026!",
            })
            self.assertEqual(changed.status_code, 200, changed.text)
            app_services.credentials.initialize()
            self.assertEqual(app_services.auth().get_admin_credentials().username, "管理员甲")
        for token in (first, second):
            self.assertEqual(self.client.get("/api/session", headers=self.headers(token)).status_code, 401)
        self.assertEqual(self.login().status_code, 401)
        self.assertEqual(self.login("管理员甲", "新密码-安全翻译系统-2026!").status_code, 200)
        stored = repositories().config.get_config("admin_password")
        self.assertTrue(stored.startswith("pbkdf2_sha256$"))
        self.assertNotIn("新密码", stored)

    def test_wrong_current_password_cannot_change_account(self):
        token = self.token()
        result = self.client.post("/api/system/credentials", headers=self.headers(token), json={
            "current_password": "wrong-password", "new_password": "another-long-password!",
        })
        self.assertEqual(result.status_code, 400)
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.client.get("/api/session", headers=self.headers(token)).status_code, 200)

    def test_empty_weak_and_unchanged_updates_do_not_mutate_account(self):
        token = self.token()
        for update in ({}, {"new_password": "admin123"}, {"new_password": "123456789012"}, {"new_username": "  "}):
            result = self.client.post("/api/system/credentials", headers=self.headers(token), json={
                "current_password": self.password, **update,
            })
            self.assertEqual(result.status_code, 400, result.text)
        self.assertEqual(app_services.auth().verify_token(token), "admin")
        self.assertEqual(app_services.auth().get_admin_credentials().username, "admin")

    def test_unicode_password_whitespace_is_not_silently_trimmed(self):
        password = "  正文翻译 可信内容 2026!  "
        reset_account("中文管理员", password)
        self.assertEqual(self.login("中文管理员", password).status_code, 200)
        self.assertEqual(self.login("中文管理员", password.strip()).status_code, 401)

    def test_five_failed_attempts_limit_even_correct_password_and_persist(self):
        for _ in range(5):
            self.assertEqual(self.login(password="wrong").status_code, 401)
        limited = self.login()
        self.assertEqual(limited.status_code, 429)
        self.assertGreater(int(limited.headers["retry-after"]), 0)
        with TestClient(app) as restarted:
            self.assertEqual(restarted.post("/api/login", data={"username": "admin", "password": self.password}).status_code, 429)
        repositories().auth.execute("UPDATE auth_attempts SET expires_at = ?", (int(time.time()) - 1,))
        self.assertEqual(self.login().status_code, 200)

    def test_parallel_attempts_cannot_bypass_limit(self):
        def attempt(_):
            try:
                app_services.credentials.login("admin", "wrong", "parallel-client")
            except APIException as error:
                return error.code
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            codes = list(executor.map(attempt, range(8)))
        self.assertEqual(codes.count(401), 5)
        self.assertEqual(codes.count(429), 3)

    def test_current_password_attempts_are_also_limited(self):
        token = self.token()
        for _ in range(5):
            result = self.client.post("/api/system/credentials", headers=self.headers(token), json={
                "current_password": "wrong", "new_password": "another-password!234",
            })
            self.assertEqual(result.status_code, 400)
        result = self.client.post("/api/system/credentials", headers=self.headers(token), json={
            "current_password": self.password, "new_password": "another-password!234",
        })
        self.assertEqual(result.status_code, 429)

    def test_global_limit_prevents_changing_ip_to_bypass(self):
        with patch.object(AuthService, "authenticate_user", return_value=False):
            for number in range(30):
                with self.assertRaises(APIException) as caught:
                    app_services.credentials.login("admin", "wrong", str(number))
                self.assertEqual(caught.exception.code, 401)
            with self.assertRaises(APIException) as caught:
                app_services.credentials.login("admin", "wrong", "new-ip")
            self.assertEqual(caught.exception.code, 429)

    def test_signed_forgery_missing_claims_and_expired_tokens_fail(self):
        token = self.token()
        service = app_services.auth()
        payload = jwt.decode(token, options={"verify_signature": False})
        forged = {**payload, "jti": "unregistered-session"}
        expired = {**payload, "exp": int(time.time()) - 1}
        missing = {key: value for key, value in payload.items() if key != "exp"}
        for altered in (forged, expired, missing):
            encoded = jwt.encode(altered, service.secret_key, algorithm="HS256")
            self.assertEqual(self.client.get("/api/session", headers=self.headers(encoded)).status_code, 401)
        self.assertEqual(self.client.get("/api/session", headers=self.headers("invalid")).status_code, 401)

    def test_rotation_and_local_recovery_invalidate_old_tokens(self):
        token = self.token()
        old_key = app_services.auth().secret_key
        reset_account("admin", "Recovered-admin!1234")
        self.assertNotEqual(app_services.auth().secret_key, old_key)
        self.assertIsNone(app_services.auth().verify_token(token))
        self.assertEqual(self.login(password="Recovered-admin!1234").status_code, 200)

    def test_environment_bootstrap_only_once_and_no_plaintext_storage(self):
        repositories().config.delete_config("admin_username")
        repositories().config.delete_config("admin_password")
        with patch.multiple(settings, ADMIN_USERNAME="initial-admin", ADMIN_PASSWORD="Initial-passphrase!123"):
            app_services.credentials.initialize()
            self.assertTrue(app_services.auth().authenticate_user("initial-admin", "Initial-passphrase!123"))
            self.assertTrue(repositories().config.get_config("admin_password").startswith("pbkdf2_sha256$"))
            reset_account("different-admin", "Different-passphrase!123")
            app_services.credentials.initialize()
            self.assertEqual(app_services.auth().get_admin_credentials().username, "different-admin")

    def test_placeholder_keys_fail_closed(self):
        with patch.object(settings, "JWT_SECRET_KEY", "replace-with-a-long-random-signing-secret-key"):
            with self.assertRaises(ConfigurationError):
                app_services.auth()

    def test_validation_does_not_echo_password(self):
        token = self.token()
        password = "Sensitive-password-" * 30
        result = self.client.post("/api/system/credentials", headers=self.headers(token), json={"current_password": password})
        self.assertEqual(result.status_code, 422)
        self.assertNotIn(password, result.text)

    def test_every_admin_route_requires_authentication(self):
        from backend.app.routers.auth import get_current_user
        def protected(dependant):
            return dependant.call is get_current_user or any(protected(dep) for dep in dependant.dependencies)
        for route in app.routes:
            if not route.path.startswith("/api/") or route.path.startswith(("/api/public/", "/api/analyst/")) or route.path == "/api/login":
                continue
            self.assertTrue(protected(route.dependant), route.path)
        for url in ("/api/session", "/api/wechat/status", "/api/spiders"):
            self.assertEqual(self.client.get(url).status_code, 401)


if __name__ == "__main__":
    unittest.main()
