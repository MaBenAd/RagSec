"""Explicit real-service lane; isolated generated names only."""
import os
import uuid
from alembic import command
from alembic.config import Config
from qdrant_client import QdrantClient, models
from sqlalchemy import create_engine, inspect, text
import pytest

from rag.vectors import VectorReader, VectorWriter


@pytest.mark.integration
def test_postgres_migration_roundtrip():
    url = os.environ.get("RAGSEC_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set RAGSEC_TEST_POSTGRES_URL for the PostgreSQL integration lane")
    url = url.replace("postgresql://", "postgresql+pg8000://", 1)
    admin = create_engine(url)
    name = "ragsec_migration_" + uuid.uuid4().hex
    with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    database_url = url.rsplit("/", 1)[0] + "/" + name
    try:
        cfg = Config("backend/alembic.ini")
        cfg.set_main_option("script_location", "backend/alembic")
        cfg.set_main_option("sqlalchemy.url", database_url)
        command.upgrade(cfg, "head")
        engine = create_engine(database_url)
        assert "security_tombstones" in inspect(engine).get_table_names()
        with engine.connect() as conn:
            assert conn.execute(text("SELECT corpus_version FROM security_state WHERE id=1")).scalar() == 1
        engine.dispose()
        command.downgrade(cfg, "20260426_0002")
        command.upgrade(cfg, "head")
    finally:
        with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text(f'DROP DATABASE "{name}"'))
        admin.dispose()


@pytest.mark.integration
def test_qdrant_read_key_cannot_write():
    url = os.environ.get("RAGSEC_TEST_QDRANT_URL")
    if not url:
        pytest.skip("Set RAGSEC_TEST_QDRANT_URL for Qdrant credential integration")
    writer = QdrantClient(url=url, api_key="synthetic-write-test-key", check_compatibility=False)
    reader = QdrantClient(url=url, api_key="synthetic-read-test-key", check_compatibility=False)
    collection = "rs_integration_" + uuid.uuid4().hex
    record = {"chunk_id": uuid.uuid4().hex, "document_id": "doc", "tenant": "alpha",
              "owner": 1, "classification": "public", "text": "Library hours"}
    try:
        VectorWriter(writer).build(collection, [record])
        assert VectorReader(reader).search(collection, "library", "alpha", 1, 5)
        assert not VectorReader(reader).search(collection, "library", "beta", 2, 5)
        with pytest.raises(Exception) as error:
            reader.upsert(collection, points=[models.PointStruct(id=uuid.uuid4().hex, vector=[0.0] * 256)])
        assert getattr(error.value, "status_code", None) == 403
    finally:
        writer.delete_collection(collection)
        writer.close()
        reader.close()
