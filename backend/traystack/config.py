from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://traystack:traystack_local@localhost:5432/traystack"
    storage_path: Path = Path("/data/blobs")
    upload_max_bytes: int = Field(default=25 * 1024 * 1024, gt=0)
    cors_origins: list[str] = ["http://localhost:8080", "http://127.0.0.1:8080"]
