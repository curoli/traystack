from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://traystack:traystack_local@localhost:5432/traystack"
    storage_path: Path = Path("/data/blobs")
    semantic_model_path: Path = Path("/opt/traystack/semantic-model")
    search_snapshot_max_bytes: int = Field(default=64_000_000, ge=100_000, le=256_000_000)
    search_snapshot_max_documents: int = Field(default=10_000, ge=1, le=100_000)
    upload_max_bytes: int = Field(default=25 * 1024 * 1024, gt=0)
    cors_origins: list[str] = ["http://localhost:8080", "http://127.0.0.1:8080"]

    ocr_languages: str = Field(default="eng", pattern=r"^[a-zA-Z0-9_]+(?:\+[a-zA-Z0-9_]+)*$")
    ocr_timeout_seconds: int = Field(default=30, ge=1, le=300)
    ocr_dpi: int = Field(default=200, ge=72, le=400)
    processing_max_pages: int = Field(default=100, ge=1, le=1000)
    processing_max_pixels: int = Field(default=25_000_000, ge=1_000_000, le=100_000_000)
    worker_poll_seconds: float = Field(default=1.0, ge=0.1, le=60)
