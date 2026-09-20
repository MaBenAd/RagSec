"""Qdrant read/write capability separation with deterministic lab embeddings.

The hash embedding has no downloaded model or external embedding API. It is an
explicit lab baseline, not a claim of multilingual semantic retrieval quality.
"""
import hashlib
import math
import re
import uuid
from qdrant_client import QdrantClient, models

EMBEDDING_VERSION = "sha256-word-hash-256-v1"


def embed(text: str) -> list[float]:
    vector = [0.0] * 256
    for word in re.findall(r"\w+", text.casefold()):
        value = hashlib.sha256(word.encode()).digest()
        vector[int.from_bytes(value[:2], "big") % 256] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


def point_id(chunk_id: str) -> str:
    return str(uuid.UUID(hex=chunk_id))


class VectorReader:
    def __init__(self, client: QdrantClient):
        self.client = client

    def search(self, collection: str, query: str, tenant: str, actor_id: int, limit: int):
        filt = models.Filter(must=[
            models.FieldCondition(key="tenant", match=models.MatchValue(value=tenant)),
            models.Filter(should=[
                models.FieldCondition(key="classification", match=models.MatchValue(value="public")),
                models.FieldCondition(key="owner", match=models.MatchValue(value=actor_id)),
            ]),
        ])
        return self.client.query_points(collection_name=collection, query=embed(query),
                                        query_filter=filt, limit=limit, with_vectors=False,
                                        score_threshold=0.05).points


class VectorWriter:
    def __init__(self, client: QdrantClient):
        self.client = client

    def build(self, collection: str, records: list[dict]):
        if not self.client.collection_exists(collection):
            self.client.create_collection(collection, vectors_config=models.VectorParams(
                size=256, distance=models.Distance.COSINE))
        if records:
            self.client.upsert(collection, points=[models.PointStruct(
                id=point_id(r["chunk_id"]), vector=embed(r["text"]), payload=r) for r in records], wait=True)
        actual = self.records(collection)
        expected = {r["chunk_id"]: r for r in records}
        if {r["chunk_id"]: r for r in actual} != expected:
            raise ValueError("index_manifest_mismatch")

    def records(self, collection: str) -> list[dict]:
        records, offset = [], None
        while True:
            points, offset = self.client.scroll(collection, offset=offset, limit=128, with_vectors=False)
            records.extend(p.payload for p in points)
            if offset is None:
                return records

    def delete_document(self, collection: str, doc_id: str):
        self.client.delete(collection, points_selector=models.FilterSelector(filter=models.Filter(must=[
            models.FieldCondition(key="document_id", match=models.MatchValue(value=doc_id))])), wait=True)

    def collections(self):
        return [item.name for item in self.client.get_collections().collections if item.name.startswith("rs_")]
