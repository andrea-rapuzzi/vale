from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    db_path: str = "./data/yts.db"
    vtt_dir: str = "./data/vtt"
    frontend_url: str = "http://localhost:4321"
    cookies_browser: str = "chrome"  # browser to export cookies from: chrome, firefox, etc. Set to "" to disable.
    cookies_max_age_hours: int = 12  # refresh cookie file after this many hours

    @property
    def db_path_resolved(self) -> Path:
        return Path(self.db_path).resolve()

    @property
    def vtt_dir_resolved(self) -> Path:
        return Path(self.vtt_dir).resolve()

    @property
    def cookies_file_resolved(self) -> Path:
        return Path(self.db_path).resolve().parent / "cookies.txt"


settings = Settings()
