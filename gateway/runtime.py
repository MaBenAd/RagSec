"""Production wiring has no bypass mode and no vector writer capability."""
import os
import httpx
import redis
from qdrant_client import QdrantClient

from backend.services.db_service import engine
from gateway.app import create_app
from gateway.cache import Cache
from gateway.citations import Citations
from gateway.config import Limits, signing_key
from gateway.errors import ControlError
from gateway.memory import Memories
from gateway.pipeline import Pipeline
from gateway.policy import Policy
from gateway.provider import ExtractiveProvider, GroqProvider
from gateway.tools import Tools
from rag.parser import Parser
from rag.retrieval import Retrieval
from rag.store import Store
from rag.vectors import VectorReader


class RemoteIngestion:
    def __init__(self):
        token = os.environ["RAGSEC_INGEST_TOKEN"]
        if len(token) < 32:
            raise RuntimeError("Weak ingestion service token")
        self.client = httpx.Client(base_url=os.environ.get("RAGSEC_INGEST_URL", "http://ingestion:8001"),
                                   headers={"Authorization": f"Bearer {token}"}, timeout=30, trust_env=False)

    def call(self, action, actor, **kwargs):
        try:
            response = self.client.post(f"/operations/{action}", json={"actor_id": actor.id, **kwargs})
            if response.status_code == 403:
                raise ControlError("ingestion_denied")
            response.raise_for_status()
            return response.json()["result"]
        except httpx.HTTPError:
            raise ControlError("ingestion_unavailable", "unavailable") from None

    def register_source(self, actor, source_id):
        return self.call("source", actor, source_id=source_id)

    def stage(self, actor, body, **kwargs):
        import base64
        original = kwargs.get("original")
        return self.call("stage", actor, upload=body.model_dump(),
                         original=base64.b64encode(original).decode() if original is not None else None,
                         parser_version=kwargs.get("parser_version", "plain-text-v1"))

    def review(self, actor, doc_id, version, approve):
        return self.call("review", actor, doc_id=doc_id, version=version, approve=approve)

    def publish(self, actor):
        return self.call("publish", actor)

    def revoke(self, actor, doc_id):
        return self.call("revoke", actor, doc_id=doc_id)


def components():
    limits = Limits()
    key = signing_key()
    store = Store(engine)
    policy = Policy(os.environ.get("RAGSEC_OPA_URL", "http://opa:8181"), token=os.environ.get("RAGSEC_OPA_TOKEN"))
    vector = QdrantClient(url=os.environ.get("QDRANT_URL", "http://qdrant:6333"),
                          api_key=os.environ["QDRANT_READ_KEY"], timeout=3, check_compatibility=False)
    redis_url = os.environ.get("RAGSEC_REDIS_URL")
    cache = Cache(key, redis=redis.Redis.from_url(redis_url, socket_timeout=0.5, socket_connect_timeout=0.5) if redis_url else None)
    provider_kind = os.environ.get("RAGSEC_PROVIDER", "offline")
    if provider_kind not in {"offline", "groq"}:
        raise RuntimeError("Unsupported provider")
    provider = ExtractiveProvider() if provider_kind == "offline" else GroqProvider(
        os.environ["GROQ_API_KEY"], os.environ["GROQ_MODEL"])
    pipeline = Pipeline(store, policy, Retrieval(store, policy, VectorReader(vector), limits), provider,
                        cache, Citations({"v1": key}), Tools(store, policy), limits)
    return pipeline


def application():
    pipeline = components()
    return create_app(pipeline, RemoteIngestion(), Memories(pipeline.store, pipeline.policy), Parser())
