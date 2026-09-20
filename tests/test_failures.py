import asyncio
import json
import subprocess
import sys
import threading
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.services.auth_service import create_access_token
from backend.services.db_service import Conversation, Message
from gateway.app import create_app
from gateway.contracts import Candidate, ChatRequest, DocumentUpload, MemoryWrite
from gateway.errors import ControlError
from gateway.policy import Policy
from rag.models import Audit, Chunk, Document, Membership, SecurityState, Tombstone
from rag.recovery import export_controls, reconcile_restore
from tests.test_boundaries import prepare, release


def test_secret_split_across_candidate_chunks(published):
    class Chunked:
        model = "chunked-double"
        async def generate(self, messages, _max_tokens):
            parts = ["RAG", "SEC_", "CANARY_", "SYNTHETIC"]
            evidence = json.loads(messages[1]["content"].split("\n", 1)[1].rsplit("\n", 1)[0])["evidence"]
            return Candidate(answer="".join(parts), source_ids=(evidence[0]["chunk_id"],))
    published.pipeline.provider = Chunked()
    app = create_app(published.pipeline, published.ingestion, published.memories)
    token = create_access_token(1, "user1@example.test", "student")
    with TestClient(app) as client:
        for path in ["/api/v1/chat", "/api/v1/chat/stream"]:
            response = client.post(path, json={"question": "library"}, headers={"Authorization": f"Bearer {token}"})
            assert "RAGSEC_CANARY" not in response.text
            assert "sensitive_data" in response.text


def test_history_never_discloses_secret(published):
    with published.store.sessions.begin() as session:
        conv = Conversation(user_id=1, title="Synthetic")
        session.add(conv)
        session.flush()
        session.add(Message(conversation_id=conv.id, role="user", content="RAGSEC_CANARY_HISTORY"))
        conv_id = conv.id
    class Spy:
        model = "spy"
        async def generate(self, *args):
            pytest.fail("Sensitive history reached provider")
    published.pipeline.provider = Spy()
    result = asyncio.run(published.pipeline.prepare(published.actors[1],
                         ChatRequest(question="library", conversation_id=conv_id)))
    assert result.outcome.reason == "sensitive_data"


def test_history_ownership_and_revoked_dependencies(published):
    outcome = release(published, prepare(published))
    request = ChatRequest(question="library", conversation_id=outcome.conversation_id)
    other = asyncio.run(published.pipeline.prepare(published.actors[2], request))
    assert other.outcome.reason == "conversation_denied"
    published.ingestion.revoke(published.actors[3], published.doc)
    result = asyncio.run(published.pipeline.prepare(published.actors[1], request))
    assert result.outcome.status == "blocked"


def test_vector_outage_has_no_model_fallback(published, monkeypatch):
    monkeypatch.setattr(published.pipeline.retrieval.reader, "search", lambda *args: (_ for _ in ()).throw(ConnectionError("secret")))
    result = prepare(published)
    assert result.outcome.reason == "retrieval_unavailable"
    assert "secret" not in result.outcome.model_dump_json()


def test_policy_outage_prevents_provider(published):
    def offline(request):
        raise httpx.ConnectError("synthetic-sensitive-error")
    policy = Policy("http://opa", transport=httpx.MockTransport(offline))
    published.pipeline.retrieval.policy = policy
    assert prepare(published).outcome.reason == "policy_unavailable"
    assert published.pipeline.tools.executions == 0


def test_cache_is_actor_bound_signed_and_optional(published):
    release(published, prepare(published))
    cache = published.pipeline.cache
    assert len(cache.entries) == 1
    key = next(iter(cache.entries))
    envelope = json.loads(cache.entries[key])
    envelope["payload"] = envelope["payload"].replace("Library", "Poisoned")
    cache.entries[key] = json.dumps(envelope)
    assert cache.get(key) is None
    assert prepare(published).outcome.status == "allowed"
    assert cache.cache_key(published.actors[1], "same", [], 1, "model") != cache.cache_key(published.actors[2], "same", [], 1, "model")
    class BrokenRedis:
        def get(self, key): raise ConnectionError()
        def setex(self, *args): raise ConnectionError()
    cache.local, cache.redis = False, BrokenRedis()
    assert release(published, prepare(published)).status == "allowed"


def test_private_response_not_cached(lab):
    doc = lab.ingestion.stage(lab.actors[3], DocumentUpload(source_id="source-alpha", classification="private", text="Library private hours"))
    lab.ingestion.review(lab.actors[3], doc, 1, True)
    lab.ingestion.publish(lab.actors[3])
    release(lab, prepare(lab, actor=3))
    assert not lab.pipeline.cache.entries


def test_restore_overlays_tombstones_and_current_grants(published):
    published.ingestion.revoke(published.actors[3], published.doc)
    with published.store.locked() as (session, _state):
        session.get(Membership, 1).enabled = False
    controls = export_controls(published.store)
    # Simulated older DB backup: current controls are retained separately.
    with published.store.locked() as (session, _state):
        session.delete(session.get(Tombstone, published.doc))
        session.get(Document, published.doc).status = "indexed"
        session.get(Membership, 1).enabled = True
    reconcile_restore(published.store, controls)
    with published.store.sessions() as session:
        assert session.get(Tombstone, published.doc)
        assert session.get(Document, published.doc).status == "revoked"
        assert not session.get(Membership, 1).enabled
        assert session.get(SecurityState, 1).collections_json == "{}"


def test_completed_revocation_serializes_after_release(published):
    result = prepare(published)
    started, finished = threading.Event(), threading.Event()
    def revoke():
        started.set()
        published.ingestion.revoke(published.actors[3], published.doc)
        finished.set()
    with published.store.locked() as (session, state):
        response = published.pipeline.release(result, session, state)
        thread = threading.Thread(target=revoke)
        thread.start()
        assert started.wait(1)
        assert not finished.wait(0.05)
        assert response.status == "allowed"
    thread.join(2)
    assert finished.is_set()


def test_cancellation_releases_concurrency(published):
    entered = asyncio.Event()
    class Slow:
        model = "slow"
        async def generate(self, *args):
            entered.set()
            await asyncio.sleep(60)
    published.pipeline.provider = Slow()
    async def run():
        task = asyncio.create_task(published.pipeline.prepare(published.actors[1], ChatRequest(question="library")))
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
    assert published.pipeline.active == 0


def test_document_expiry_and_memory_expiry(published):
    key = published.memories.write(published.actors[1], MemoryWrite(text="French please", ttl_seconds=60))
    now = published.store.clock()
    with published.store.locked() as (session, _):
        session.get(Document, published.doc).expires_at = now + 10
    published.store.clock = lambda: now + 61
    assert prepare(published).outcome.status == "blocked"
    with pytest.raises(ControlError):
        published.memories.operation(published.actors[1], key)


def test_safe_audit_and_oversized_api(published):
    result = prepare(published, "RAGSEC_CANARY_SYNTHETIC")
    release(published, result)
    with published.store.sessions() as session:
        records = session.scalars(select(Audit)).all()
        assert records and "RAGSEC_CANARY" not in str([r.__dict__ for r in records])
    with TestClient(create_app(published.pipeline, published.ingestion, published.memories)) as client:
        response = client.post("/api/v1/chat", content="x" * 65537)
        assert response.status_code == 413


@pytest.mark.parametrize("data", [b"not a PDF", b"%PDF-1.4\nmalformed", b"%PDF-" + b"x" * (2 * 1024**2)])
def test_pdf_rejects_malformed_and_expansion(data):
    process = subprocess.run([sys.executable, "-I", "rag/pdf_worker.py"], input=data,
                             capture_output=True, timeout=12, env={"PATH": "/usr/bin"})
    assert process.returncode != 0
    assert not process.stdout
