
import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENVIRONMENT = (os.getenv("AINEWS_ENV") or os.getenv("ENV") or "development").strip().lower()
if ENVIRONMENT not in {"development", "production", "test"}:
    raise RuntimeError(f"不支持的运行环境: {ENVIRONMENT}")

env_file = PROJECT_ROOT / f".env.{ENVIRONMENT}"
load_dotenv(env_file)


def _source_version() -> str:
    version_file = PROJECT_ROOT / "VERSION"
    try:
        return version_file.read_text(encoding="utf-8").strip() or "unreleased"
    except OSError:
        return "unreleased"


SOURCE_VERSION = _source_version()

class Settings:
    PROJECT_NAME: str = "AINews Admin API"
    APP_VERSION: str = (os.getenv("APP_VERSION") or SOURCE_VERSION).strip()
    ENV: str = ENVIRONMENT
    
    # CORS
    ALLOWED_ORIGINS_STR: str = os.getenv('ALLOWED_ORIGINS', 'http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173')
    @property
    def ALLOWED_ORIGINS(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS_STR.split(',')]

    # Auth
    JWT_SECRET_KEY: str = os.getenv('JWT_SECRET_KEY', '')
    ADMIN_USERNAME: str = os.getenv('ADMIN_USERNAME', '')
    ADMIN_PASSWORD: str = os.getenv('ADMIN_PASSWORD', '')

    # AI & 3rd Party
    TELEGRAM_BOT_TOKEN: str = os.getenv('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID: str = os.getenv('TELEGRAM_CHAT_ID', '')
    PUBLIC_SITE_URL: str = os.getenv(
        "PUBLIC_SITE_URL",
        "" if ENVIRONMENT == "production" else "http://localhost:5173",
    ).rstrip("/")
    PUBLIC_HOME_URL: str = os.getenv("PUBLIC_HOME_URL", "").strip()
    PUBLIC_TELEGRAM_URL: str = os.getenv("PUBLIC_TELEGRAM_URL", "").strip()
    PUBLIC_X_URL: str = os.getenv("PUBLIC_X_URL", "").strip()
    PUBLIC_BLOG_URL: str = os.getenv("PUBLIC_BLOG_URL", "").strip()
    PUBLIC_GITHUB_URL: str = os.getenv("PUBLIC_GITHUB_URL", "").strip()
    PUBLIC_BINANCE_URL: str = os.getenv("PUBLIC_BINANCE_URL", "").strip()
    PUBLIC_OKX_URL: str = os.getenv("PUBLIC_OKX_URL", "").strip()
    PUBLIC_TUTORIAL_URL: str = os.getenv("PUBLIC_TUTORIAL_URL", "").strip()

    @property
    def PUBLIC_LINKS(self) -> dict[str, str]:
        return {
            "home": self.PUBLIC_HOME_URL,
            "telegram": self.PUBLIC_TELEGRAM_URL,
            "x": self.PUBLIC_X_URL,
            "blog": self.PUBLIC_BLOG_URL,
            "github": self.PUBLIC_GITHUB_URL,
            "binance": self.PUBLIC_BINANCE_URL,
            "okx": self.PUBLIC_OKX_URL,
            "tutorial": self.PUBLIC_TUTORIAL_URL,
        }

    def validate(self) -> None:
        if self.ENV != "production":
            return
        problems = []
        placeholder_markers = ("change-me", "changeme", "replace", "placeholder", "example", "your_")

        def is_placeholder(value: str) -> bool:
            normalized = (value or "").strip().lower()
            return not normalized or any(marker in normalized for marker in placeholder_markers)

        if not self.APP_VERSION or self.APP_VERSION == "unreleased":
            problems.append("生产环境必须使用明确的源码 VERSION")
        elif self.APP_VERSION != SOURCE_VERSION:
            problems.append(f"APP_VERSION 必须与源码 VERSION {SOURCE_VERSION} 一致")
        if len(self.JWT_SECRET_KEY) < 32 or is_placeholder(self.JWT_SECRET_KEY) or len(set(self.JWT_SECRET_KEY)) < 12:
            problems.append("JWT_SECRET_KEY 必须是至少 32 位且非占位符的随机值")
        if not self.ADMIN_USERNAME or not self.ADMIN_PASSWORD:
            problems.append("生产环境必须配置管理员账号和密码")
        elif len(self.ADMIN_PASSWORD) < 12 or is_placeholder(self.ADMIN_PASSWORD) or self.ADMIN_PASSWORD == self.ADMIN_USERNAME:
            problems.append("生产环境管理员密码至少 12 位，且不能是占位符或与用户名相同")
        if any("localhost" in origin or "127.0.0.1" in origin for origin in self.ALLOWED_ORIGINS):
            problems.append("生产环境 ALLOWED_ORIGINS 不能包含本机开发地址")
        if "*" in self.ALLOWED_ORIGINS:
            problems.append("生产环境 ALLOWED_ORIGINS 不能使用通配符")
        if not self.PUBLIC_SITE_URL:
            problems.append("生产环境必须显式配置 PUBLIC_SITE_URL")
        elif not self.PUBLIC_SITE_URL.startswith("https://"):
            problems.append("生产环境 PUBLIC_SITE_URL 必须使用 https://")
        invalid_public_links = [
            name for name, value in self.PUBLIC_LINKS.items() if value and not value.startswith("https://")
        ]
        if invalid_public_links:
            problems.append("生产环境公开链接必须使用 https://：" + ", ".join(invalid_public_links))
        if problems:
            raise RuntimeError("生产配置无效：" + "；".join(problems))

settings = Settings()
