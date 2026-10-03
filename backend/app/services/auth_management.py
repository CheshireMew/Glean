from typing import Optional
import hashlib
import math
import time

from ..core.exceptions import APIException, AuthenticationError, BusinessError, ValidationError
from .auth_service import AUTH_VERSION_KEY, AuthService, validate_password, validate_username


class CredentialService:
    def __init__(self, transaction):
        self._transaction = transaction

    def initialize(self):
        with self._transaction() as repos:
            AuthService(repos.config, repos.auth).migrate_database_password()

    def reserve_attempt(self, scope: str, client: str):
        client_key = hashlib.sha256(client.encode("utf-8")).hexdigest()
        with self._transaction() as repos:
            wait = repos.auth.reserve_attempt(scope, client_key, int(time.time()))
        if wait:
            raise APIException(f"尝试次数过多，请在 {math.ceil(wait / 60)} 分钟后重试", code=429,
                               headers={"Retry-After": str(wait)})
        return client_key

    def login(self, username: str, password: str, client: str) -> str:
        client_key = self.reserve_attempt("login", client)
        with self._transaction() as repos:
            auth_service = AuthService(repos.config, repos.auth)
            if not auth_service.authenticate_user(username, password):
                raise AuthenticationError("用户名或密码错误", headers={"WWW-Authenticate": "Bearer"})
            token = auth_service.create_access_token({"sub": username.strip()})
            repos.auth.finish_successful_attempt("login", client_key)
            return token

    def update_credentials(
        self,
        current_username: str,
        current_password: str,
        new_username: Optional[str],
        new_password: Optional[str],
        client: str = "local-cli",
    ):
        if not new_username and not new_password:
            raise ValidationError("请填写新用户名或新密码")
        username = validate_username(new_username) if new_username else current_username
        if username == current_username and not new_password:
            raise ValidationError("账户信息没有变化")
        if new_password:
            validate_password(new_password, username)
        client_key = self.reserve_attempt("credentials", client)
        validation_error = None
        with self._transaction() as repos:
            auth_service = AuthService(repos.config, repos.auth)
            if not auth_service.authenticate_user(current_username, current_password):
                raise BusinessError("当前密码错误")
            if new_password:
                if auth_service.verify_password(new_password, auth_service.get_admin_credentials().password):
                    validation_error = ValidationError("新密码不能与当前密码相同")
            elif auth_service.authenticate_user(current_username, username):
                validation_error = ValidationError("用户名不能与密码相同")
            if validation_error is None:
                if new_password:
                    repos.config.set_config("admin_password", auth_service.hash_password(new_password))
                repos.config.set_config("admin_username", username)
                current_version = int(repos.config.get_config(AUTH_VERSION_KEY) or "1")
                repos.config.set_config(AUTH_VERSION_KEY, str(current_version + 1))
                repos.auth.revoke_all_sessions()
            repos.auth.finish_successful_attempt("credentials", client_key)
        if validation_error:
            raise validation_error
        return {"message": "账户信息已更新"}
