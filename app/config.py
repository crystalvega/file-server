import os
import secrets
from pathlib import Path
from pydantic_settings import BaseSettings

def get_or_create_secret_key() -> str:
    env_key = os.getenv("SECRET_KEY")
    if env_key:
        return env_key
    data_dir = os.getenv("DATA_DIR", "/data")
    key_file = Path(data_dir) / ".secret_key"
    if key_file.exists():
        try:
            k = key_file.read_text().strip()
            if k:
                return k
        except Exception:
            pass
    new_key = secrets.token_hex(32)
    try:
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_text(new_key)
    except Exception:
        pass
    return new_key

class Settings(BaseSettings):
    APP_NAME: str = "Corporate File Share"
    DATA_DIR: str = "/data"
    PUBLIC_BASE_URL: str = ""  # e.g. "https://mail.szma-inform.ru"
    URL_PREFIX: str = os.getenv("URL_PREFIX", "/file-server")
    DEFAULT_TTL_DAYS: int = 28
    MAX_TTL_DAYS: int = 28
    MAX_FILE_SIZE_MB: int = 10240  # 10 GB limit per file
    MAX_UPLOAD_FILES: int = 20
    SECRET_KEY: str = ""
    RATE_LIMIT_ATTEMPTS: int = 5
    RATE_LIMIT_LOCKOUT_MINUTES: int = 15
    SESSION_COOKIE_NAME: str = "file_share_auth"
    SESSION_MAX_AGE_HOURS: int = 2
    API_KEY: str = os.getenv("API_KEY", os.getenv("FILE_SERVER_API_KEY", ""))
    YARA_SCANNER_URL: str = os.getenv("YARA_SCANNER_URL", "")  # e.g. "http://yara.szma-inform.ru/scan" or internal
    CLEANUP_INTERVAL_MINUTES: int = 60

    def __init__(self, **values):
        super().__init__(**values)
        if not self.SECRET_KEY:
            self.SECRET_KEY = get_or_create_secret_key()

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
