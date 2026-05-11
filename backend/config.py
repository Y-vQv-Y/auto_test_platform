"""全局配置管理"""
from pydantic_settings import BaseSettings
from typing import Optional, List
import os


class Settings(BaseSettings):
    # 应用基础配置
    APP_NAME: str = "AI自动测试平台"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # 数据库
    DATABASE_URL: str = "sqlite:///./data/test_platform.db"

    # JWT — 生产环境必须通过环境变量覆盖
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # Fernet 加密密钥 (用于加密数据库中的 AI API Key)
    # 生成方式: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    FERNET_KEY: str = ""

    # 服务端口
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS — 允许的前端来源列表
    CORS_ORIGINS: List[str] = ["*"]
    URL_WHITELIST: List[str] = []
    URL_WHITELIST_ENABLED: bool = False   # 默认关闭白名单（放通所有 URL）
    TOOL_WHITELIST_ENABLED: bool = True
    READONLY_MODE: bool = False
    AUTO_ROLLBACK_ENABLED: bool = True

    # AI 默认配置
    DEFAULT_AI_PROVIDER: str = "openai"
    DEFAULT_AI_MODEL: str = "gpt-4"

    # 测试报告路径
    REPORT_DIR: str = "./test_reports"
    GENERATED_TEST_DIR: str = "./generated_tests"

    # Playwright 配置
    PLAYWRIGHT_HEADLESS: bool = True
    PLAYWRIGHT_TIMEOUT: int = 30000

    # WebSocket
    WS_HEARTBEAT_INTERVAL: int = 30

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# 将相对路径转为绝对路径，确保子进程（pytest）在任何 CWD 下都能正确解析
settings.GENERATED_TEST_DIR = os.path.abspath(settings.GENERATED_TEST_DIR)
settings.REPORT_DIR = os.path.abspath(settings.REPORT_DIR)

# 生产环境安全检查
if not settings.SECRET_KEY and not settings.DEBUG:
    import warnings
    warnings.warn("WARNING: SECRET_KEY is empty in non-debug mode. Set SECRET_KEY in .env for production.", RuntimeWarning)
