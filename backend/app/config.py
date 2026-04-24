from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    db_path: str = "./data/yts.db"
    vtt_dir: str = "./data/vtt"
    frontend_url: str = "http://localhost:4321"

    @property
    def db_path_resolved(self) -> Path:
        return Path(self.db_path).resolve()

    @property
    def vtt_dir_resolved(self) -> Path:
        return Path(self.vtt_dir).resolve()


settings = Settings()
