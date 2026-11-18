import os
import secrets
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "Corporate File Share"
    DATA_DIR: str = "/data"
    PUBLIC_BASE_URL: str = ""  # e.g. "https://mail.szma-inform.ru"
    URL_PREFIX: str = "/files"  # or "/file-server"
    DEFAULT_TTL_DAYS: int = 28
    MAX_TTL_DAYS: int = 28
    MAX_FILE_SIZE_MB: int = 10240  # 10 GB limit per file
    MAX_UPLOAD_FILES: int = 20
    SECRET_KEY: str = os.getenv("SECRET_KEY", secrets.token_hex(32))
    RATE_LIMIT_ATTEMPTS: int = 5
    RATE_LIMIT_LOCKOUT_MINUTES: int = 15
    SESSION_COOKIE_NAME: str = "file_share_auth"
    SESSION_MAX_AGE_HOURS: int = 2
    YARA_SCANNER_URL: str = os.getenv("YARA_SCANNER_URL", "")  # e.g. "http://yara.szma-inform.ru/scan" or internal
    CLEANUP_INTERVAL_MINUTES: int = 60

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
