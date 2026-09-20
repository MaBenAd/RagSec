import json
import os
import subprocess
from types import SimpleNamespace

import httpx
import pytest
from qdrant_client import QdrantClient
from sqlalchemy import create_engine

from backend.services.db_service import Base, User
from gateway.cache import Cache
from gateway.citations import Citations
from gateway.config import Limits
from gateway.contracts import DocumentUpload
from gateway.memory import Memories
from gateway.pipeline import Pipeline
from gateway.policy import Policy
from gateway.provider import ExtractiveProvider
from gateway.tools import Tools
from rag.ingestion import Ingestion
from rag.models import Membership, SecurityState
from rag.retrieval import Retrieval
from rag.store import Store
from rag.vectors import VectorReader, VectorWriter

GRANTS = ["read", "cite", "download", "tool", "memory_read", "memory_write", "memory_delete"]
ADMIN = GRANTS + ["ingest", "approve", "delete", "publish", "manage"]


@pytest.fixture(scope="session")
def policy():
    """Real OPA for every authorization assertion, never an allow-only fake."""
    url = os.getenv("RAGSEC_TEST_OPA_URL", "http://127.0.0.1:18181")
    client = Policy(url)
    if not client.ready():
        pytest.fail("Real OPA required: start the test services documented in docs/testing.md")
    return client


@pytest.fixture
def lab(tmp_path, policy):
    engine = create_engine(f"sqlite:///{tmp_path / 'lab.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    store = Store(engine)
    with store.sessions.begin() as session:
        session.add(SecurityState(id=1, corpus_version=1, collections_json="{}"))
        for actor_id, tenant, role in [(1, "alpha", "member"), (2, "beta", "member"),
                                        (3, "alpha", "admin"), (4, "beta", "admin")]:
            session.add(User(id=actor_id, email=f"user{actor_id}@example.test", password="unused",
                             role="admin" if role == "admin" else "student", language="en"))
            session.add(Membership(user_id=actor_id, tenant=tenant, role=role, enabled=True,
                                   access_version=1, grants_json=json.dumps(ADMIN if role == "admin" else GRANTS)))
    client = QdrantClient(":memory:")
    writer = VectorWriter(client)
    limits = Limits()
    ingestion = Ingestion(store, policy, writer)
    actors = {i: store.actor(i) for i in range(1, 5)}
    for actor_id in [3, 4]:
        ingestion.register_source(actors[actor_id], f"source-{actors[actor_id].tenant}")
    key = b"synthetic-citation-test-key-0000000000000"
    pipeline = Pipeline(store, policy, Retrieval(store, policy, VectorReader(client), limits),
                        ExtractiveProvider(), Cache(key, local=True), Citations({"v1": key}),
                        Tools(store, policy), limits)
    yield SimpleNamespace(store=store, pipeline=pipeline, actors=actors, ingestion=ingestion,
                          vectors=client, writer=writer, memories=Memories(store, policy), tmp=tmp_path)
    client.close()
    engine.dispose()


@pytest.fixture
def published(lab):
    doc = lab.ingestion.stage(lab.actors[3], DocumentUpload(source_id="source-alpha", classification="public",
                              text="Library bibliothèque مكتبة opening hours: Monday 09:00 to 17:00."))
    lab.ingestion.review(lab.actors[3], doc, 1, True)
    lab.ingestion.publish(lab.actors[3])
    lab.doc = doc
    return lab
