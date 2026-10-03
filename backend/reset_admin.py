"""Local administrator recovery; never exposes a password-reset HTTP endpoint."""
import argparse
from getpass import getpass
import secrets

from backend.app.core.exceptions import APIException
from backend.app.infrastructure.database import init_database
from backend.app.infrastructure.repositories import transactional_repositories
from backend.app.services.auth_service import AUTH_VERSION_KEY, AuthService, validate_password, validate_username


def reset_account(username: str, password: str):
    username = validate_username(username)
    validate_password(password, username)
    init_database()
    with transactional_repositories() as repos:
        repos.config.set_config("admin_username", username)
        repos.config.set_config("admin_password", AuthService.hash_password(password))
        repos.config.set_config("jwt_secret_key", secrets.token_urlsafe(48))
        version = int(repos.config.get_config(AUTH_VERSION_KEY) or "1")
        repos.config.set_config(AUTH_VERSION_KEY, str(version + 1))
        repos.auth.revoke_all_sessions()
        repos.auth.execute("DELETE FROM auth_attempts")


def main():
    parser = argparse.ArgumentParser(description="在本机设置管理员账号并使所有旧登录失效")
    parser.add_argument("--username", default="admin", help="管理员用户名，默认 admin")
    args = parser.parse_args()
    password = getpass("新密码（至少 12 位，不会显示）：")
    if password != getpass("确认新密码："):
        parser.error("两次输入的密码不一致")
    try:
        reset_account(args.username, password)
    except APIException as error:
        parser.error(error.message)
    print(f"管理员 {args.username.strip()} 已更新，旧登录已全部失效。")


if __name__ == "__main__":
    main()
