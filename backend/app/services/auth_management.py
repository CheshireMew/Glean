from typing import Optional

from ..core.exceptions import BusinessError, ValidationError
from .auth_service import AUTH_VERSION_KEY, AuthService


class CredentialService:
    def __init__(self, transaction):
        self._transaction = transaction

    def update_credentials(
        self,
        current_username: str,
        current_password: str,
        new_username: Optional[str],
        new_password: Optional[str],
    ):
        with self._transaction() as repos:
            auth_service = AuthService(repos.config)
            if auth_service.is_environment_managed():
                raise BusinessError("当前管理员账号由环境变量管理，不能在后台修改")
            if not auth_service.authenticate_user(current_username, current_password):
                raise BusinessError("当前密码错误")
            if new_username:
                if len(new_username) < 3:
                    raise ValidationError("用户名长度至少为3个字符")
                repos.config.set_config("admin_username", new_username)
            if new_password:
                if len(new_password) < 6:
                    raise ValidationError("密码长度至少为6个字符")
                repos.config.set_config("admin_password", auth_service.hash_password(new_password))
            if new_username or new_password:
                current_version = int(repos.config.get_config(AUTH_VERSION_KEY) or "1")
                repos.config.set_config(AUTH_VERSION_KEY, str(current_version + 1))
            return {"message": "账户信息已更新"}
