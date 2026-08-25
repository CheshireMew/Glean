from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Protocol
import base64
import hashlib
import hmac
import os

import jwt
from pydantic import BaseModel

from ..core.config import settings
from ..core.exceptions import ConfigurationError

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12
PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 310_000
AUTH_VERSION_KEY = "auth_token_version"

class Token(BaseModel):
    access_token: str
    token_type: str


class ConfigStore(Protocol):
    def get_config(self, key: str) -> Optional[str]:
        ...

    def set_config(self, key: str, value: str):
        ...


@dataclass(frozen=True)
class AdminCredentials:
    source: str
    username: str
    password: str


class AuthService:
    def __init__(self, config_repo: ConfigStore):
        self.config_repo = config_repo
        self.secret_key = self._get_or_create_secret_key()

    def _get_or_create_secret_key(self) -> str:
        if settings.JWT_SECRET_KEY:
            return settings.JWT_SECRET_KEY
            
        import secrets
        key = self.config_repo.get_config("jwt_secret_key")
        if not key:
            key = secrets.token_urlsafe(32)
            self.config_repo.set_config("jwt_secret_key", key)
        return key

    def migrate_database_password(self) -> bool:
        stored_password = self.config_repo.get_config("admin_password") or ""
        if not stored_password or stored_password.startswith(f"{PASSWORD_SCHEME}$"):
            return False
        self.config_repo.set_config("admin_password", self.hash_password(stored_password.strip()))
        return True

    @staticmethod
    def _normalize_credentials(source: str, username: str | None, password: str | None) -> AdminCredentials | None:
        normalized_username = (username or "").strip()
        normalized_password = (password or "").strip()
        if not normalized_username and not normalized_password:
            return None
        if not normalized_username or not normalized_password:
            raise ConfigurationError(f"{source} 管理员账号配置不完整")
        return AdminCredentials(source=source, username=normalized_username, password=normalized_password)

    def get_admin_credentials(self) -> AdminCredentials:
        env_credentials = self._normalize_credentials("环境变量", settings.ADMIN_USERNAME, settings.ADMIN_PASSWORD)
        if env_credentials:
            return env_credentials

        db_credentials = self._normalize_credentials(
            "数据库",
            self.config_repo.get_config("admin_username"),
            self.config_repo.get_config("admin_password"),
        )
        if db_credentials:
            return db_credentials

        raise ConfigurationError("管理员账号未配置，请先设置环境变量或后台配置")

    def is_environment_managed(self) -> bool:
        return self._normalize_credentials("环境变量", settings.ADMIN_USERNAME, settings.ADMIN_PASSWORD) is not None

    def authenticate_user(self, username: str, password: str) -> bool:
        credentials = self.get_admin_credentials()
        username_ok = hmac.compare_digest(username, credentials.username)
        password_ok = self.verify_password(password, credentials.password)
        return username_ok and password_ok

    def create_access_token(self, data: dict) -> str:
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire, "ver": self.config_repo.get_config(AUTH_VERSION_KEY) or "1"})
        return jwt.encode(to_encode, self.secret_key, algorithm=ALGORITHM)

    def verify_token(self, token: str) -> Optional[str]:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            token_version = str(payload.get("ver") or "")
            credentials = self.get_admin_credentials()
            current_version = self.config_repo.get_config(AUTH_VERSION_KEY) or "1"
            if not username or not hmac.compare_digest(username, credentials.username):
                return None
            if not hmac.compare_digest(token_version, current_version):
                return None
            return username
        except jwt.PyJWTError:
            return None
        except Exception:
            return None

    @staticmethod
    def hash_password(password: str) -> str:
        salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
        return "$".join(
            [
                PASSWORD_SCHEME,
                str(PASSWORD_ITERATIONS),
                base64.urlsafe_b64encode(salt).decode("ascii"),
                base64.urlsafe_b64encode(digest).decode("ascii"),
            ]
        )

    @staticmethod
    def verify_password(password: str, encoded: str) -> bool:
        if not encoded.startswith(f"{PASSWORD_SCHEME}$"):
            return hmac.compare_digest(password, encoded)
        try:
            _, iterations, salt_value, digest_value = encoded.split("$", 3)
            salt = base64.urlsafe_b64decode(salt_value.encode("ascii"))
            expected = base64.urlsafe_b64decode(digest_value.encode("ascii"))
            actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
            return hmac.compare_digest(actual, expected)
        except Exception:
            return False
