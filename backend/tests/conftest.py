import os
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from alembic import command
from traystack.config import Settings
from traystack.main import create_app

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def database_url():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a dedicated PostgreSQL *_test database")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or not (parsed.database or "").endswith("_test"):
        pytest.fail("Integration tests require a dedicated PostgreSQL database ending in _test")
    return url


@pytest.fixture(scope="session")
def engine(database_url):
    engine = create_engine(database_url)
    # Refuse unexpected tables; only the dedicated test schema may be reused.
    with engine.connect() as connection:
        tables = (
            connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
            .scalars()
            .all()
        )
        if set(tables) - {
            "documents",
            "revisions",
            "artifacts",
            "alembic_version",
            "processing_jobs",
            "revision_texts",
            "page_texts",
            "passage_reviews",
            "search_runs",
            "archived_texts",
            "search_run_sources",
        }:
            pytest.fail("Unexpected tables in test database; use a dedicated test database")
    config = Config(str(ROOT / "backend" / "alembic.ini"))
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        command.upgrade(config, "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
    yield engine
    engine.dispose()


@pytest.fixture
def client(engine, database_url, tmp_path):
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE search_runs, page_texts, revision_texts, processing_jobs, "
                "artifacts, revisions, documents CASCADE"
            )
        )
    settings = Settings(
        database_url=database_url, storage_path=tmp_path / "blobs", upload_max_bytes=1024 * 1024
    )
    with TestClient(create_app(settings)) as client:
        yield client
