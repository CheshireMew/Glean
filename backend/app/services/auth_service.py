from dataclasses import dataclass
from typing import Optional, Protocol
import base64
import hashlib
import hmac
import os
import secrets
import time
import unicodedata

import jwt
from pydantic import BaseModel

from ..core.config import settings
from ..core.exceptions import ConfigurationError, ValidationError
from ..core.revoked_credentials import is_revoked

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12
PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 310_000
AUTH_VERSION_KEY = "auth_token_version"
TOKEN_ISSUER = "glean-admin"
TOKEN_AUDIENCE = "glean-api"


def safe_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def validate_username(username: str) -> str:
    username = username.strip()
    if not 3 <= len(username) <= 64 or any(unicodedata.category(c).startswith("C") for c in username):
        raise ValidationError("用户名需要 3–64 个字符，不能包含控制字符")
    return username


def validate_password(password: str, username: str) -> None:
    if is_revoked('ADMIN_PASSWORD', password):
        raise ValidationError('该密码曾进入仓库历史，请使用全新的密码')
    if not 12 <= len(password) <= 256:
        raise ValidationError("密码需要 12–256 个字符")
    value = password.strip().casefold()
    if len(value) < 12 or len(set(value)) < 5 or value.isdecimal() or value == username.casefold() or value in {
        "password1234", "password12345", "admin12345678", "123456abcdef", "qwerty1234567",
        "replace-with-a-strong-password",
    }:
        raise ValidationError("密码过于简单，请使用较长且不容易猜到的密码")


def valid_signing_key(key: str) -> bool:
    return not is_revoked('JWT_SECRET_KEY', key) and len(key) >= 32 and len(set(key)) >= 12 and not any(
        marker in key.lower() for marker in ("change-me", "changeme", "replace", "placeholder", "example", "your_")
    )

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
    def __init__(self, config_repo: ConfigStore, session_repo):
        self.config_repo = config_repo
        self.session_repo = session_repo
        self.secret_key = self._get_or_create_secret_key()

    def _get_or_create_secret_key(self) -> str:
        if settings.JWT_SECRET_KEY:
            if not valid_signing_key(settings.JWT_SECRET_KEY):
                raise ConfigurationError("登录签名密钥不安全，请更换随机密钥，或留空由系统生成")
            return settings.JWT_SECRET_KEY

        key = self.config_repo.get_config("jwt_secret_key")
        if not key:
            key = secrets.token_urlsafe(32)
            self.config_repo.set_config("jwt_secret_key", key)
        if not valid_signing_key(key):
            raise ConfigurationError("数据库中的登录签名密钥不安全，请运行本地账户重置命令")
        return key

    def migrate_database_password(self) -> bool:
        stored_password = self.config_repo.get_config("admin_password") or ""
        if not stored_password and not self.config_repo.get_config("admin_username"):
            initial = self._normalize_credentials("环境变量", settings.ADMIN_USERNAME, settings.ADMIN_PASSWORD)
            if initial:
                username = validate_username(initial.username)
                validate_password(initial.password, username)
                self.config_repo.set_config("admin_username", username)
                self.config_repo.set_config("admin_password", self.hash_password(initial.password))
                return True
        if not stored_password or stored_password.startswith(f"{PASSWORD_SCHEME}$"):
            return False
        self.config_repo.set_config("admin_password", self.hash_password(stored_password))
        return True

    @staticmethod
    def _normalize_credentials(source: str, username: str | None, password: str | None) -> AdminCredentials | None:
        normalized_username = (username or "").strip()
        normalized_password = password or ""
        if not normalized_username and not normalized_password:
            return None
        if not normalized_username or not normalized_password:
            raise ConfigurationError(f"{source} 管理员账号配置不完整")
        return AdminCredentials(source=source, username=normalized_username, password=normalized_password)

    def get_admin_credentials(self) -> AdminCredentials:
        db_credentials = self._normalize_credentials(
            "数据库",
            self.config_repo.get_config("admin_username"),
            self.config_repo.get_config("admin_password"),
        )
        if db_credentials:
            return db_credentials

        raise ConfigurationError("管理员账号尚未初始化，请在本机运行 python -m backend.reset_admin")

    def authenticate_user(self, username: str, password: str) -> bool:
        credentials = self.get_admin_credentials()
        if is_revoked('ADMIN_PASSWORD', password):
            return False
        if len(username) > 64 or len(password) > 256:
            return False
        username_ok = safe_equal(username.strip(), credentials.username)
        password_ok = self.verify_password(password, credentials.password)
        return username_ok and password_ok

    def create_access_token(self, data: dict) -> str:
        username = self.get_admin_credentials().username
        if data.get("sub") != username:
            raise ConfigurationError("不能为未知管理员创建登录状态")
        now = int(time.time())
        expire = now + ACCESS_TOKEN_EXPIRE_MINUTES * 60
        session_id = secrets.token_urlsafe(32)
        to_encode = {"sub": username, "exp": expire, "iat": now, "jti": session_id,
                     "ver": self.config_repo.get_config(AUTH_VERSION_KEY) or "1",
                     "iss": TOKEN_ISSUER, "aud": TOKEN_AUDIENCE}
        self.session_repo.create_session(session_id, username, expire, now)
        return jwt.encode(to_encode, self.secret_key, algorithm=ALGORITHM)

    def _decode_token(self, token: str) -> dict:
        return jwt.decode(token, self.secret_key, algorithms=[ALGORITHM],
                          issuer=TOKEN_ISSUER, audience=TOKEN_AUDIENCE,
                          options={"require": ["exp", "iat", "sub", "ver", "jti", "iss", "aud"]})

    def verify_token(self, token: str) -> Optional[str]:
        try:
            payload = self._decode_token(token)
            username: str = payload.get("sub")
            token_version = str(payload.get("ver") or "")
            credentials = self.get_admin_credentials()
            current_version = self.config_repo.get_config(AUTH_VERSION_KEY) or "1"
            if not isinstance(username, str) or not safe_equal(username, credentials.username):
                return None
            if not safe_equal(token_version, current_version):
                return None
            if not isinstance(payload["jti"], str) or not self.session_repo.session_active(payload["jti"], username, int(time.time())):
                return None
            return username
        except jwt.PyJWTError:
            return None
        except Exception:
            return None

    def revoke_token(self, token: str) -> None:
        try:
            payload = self._decode_token(token)
            self.session_repo.revoke_session(payload["jti"])
        except jwt.PyJWTError:
            pass

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
            return safe_equal(password, encoded)
        try:
            _, iterations, salt_value, digest_value = encoded.split("$", 3)
            salt = base64.urlsafe_b64decode(salt_value.encode("ascii"))
            expected = base64.urlsafe_b64decode(digest_value.encode("ascii"))
            actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
            return hmac.compare_digest(actual, expected)
        except Exception:
            return False
