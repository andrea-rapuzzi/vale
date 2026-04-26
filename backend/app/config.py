from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    database_url: str = ""  # Postgres connection string (Supabase: pooler URL recommended)
    frontend_url: str = "http://localhost:4321"
    cookies_browser: str = "chrome"  # browser to export cookies from: chrome, firefox, etc. Set to "" to disable.
    cookies_max_age_hours: int = 12  # refresh cookie file after this many hours
    cookies_dir: str = "./data"  # local directory for the cached cookies.txt file

    @property
    def cookies_file_resolved(self) -> Path:
        p = Path(self.cookies_dir).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p / "cookies.txt"


settings = Settings()
