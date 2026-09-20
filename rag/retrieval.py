import json
from dataclasses import dataclass

from gateway.errors import ControlError
from rag.ingestion import Ingestion
from rag.models import Chunk
from rag.store import digest, resource
from scanners.inspection import disclosure_gate, inspect_text


@dataclass(frozen=True)
class Evidence:
    chunk_id: str
    document_id: str
    version: int
    access_version: int
    content_hash: str
    document_hash: str
    classification: str
    text: str


class Retrieval:
    def __init__(self, store, policy, reader, limits):
        self.store, self.policy, self.reader, self.limits = store, policy, reader, limits

    def verify(self, actor, evidence, session):
        self.store.current(actor, session)
        doc = self.store.document(evidence.document_id, session)
        self.policy.require(actor, "read", resource(doc))
        chunk = session.get(Chunk, evidence.chunk_id)
        if (not chunk or chunk.document_id != doc.id or chunk.version != doc.version
                or doc.version != evidence.version or doc.access_version != evidence.access_version
                or chunk.content_hash != evidence.content_hash or digest(chunk.text) != chunk.content_hash
                or doc.original_hash != evidence.document_hash or digest(doc.text) != doc.extraction_hash):
            raise ControlError("manifest_mismatch")
        return doc, chunk

    def retrieve(self, actor, question, request_id):
        mismatch_id = None
        try:
            with self.store.locked() as (session, state):
                self.store.current(actor, session)
                collection = json.loads(state.collections_json).get(actor.tenant)
                if not collection:
                    return (), state.corpus_version
                points = self.reader.search(collection, question, actor.tenant, actor.id, self.limits.chunks)
                evidence = []
                contributions = {}
                for point in points:
                    p = point.payload
                    if not isinstance(p, dict) or "document_id" not in p or "chunk_id" not in p:
                        raise ControlError("manifest_missing")
                    doc = self.store.document(p["document_id"], session)
                    self.policy.require(actor, "read", resource(doc))
                    chunk = session.get(Chunk, p["chunk_id"])
                    if (not chunk or chunk.document_id != doc.id
                            or p != Ingestion.payload(doc, chunk) or digest(chunk.text) != chunk.content_hash
                            or digest(doc.text) != doc.extraction_hash):
                        mismatch_id = doc.id
                        raise ControlError("manifest_mismatch")
                    used = contributions.get(doc.id, 0)
                    if used + len(chunk.text) > self.limits.source_chars:
                        continue
                    contributions[doc.id] = used + len(chunk.text)
                    evidence.append(Evidence(chunk.id, doc.id, doc.version, doc.access_version,
                                             chunk.content_hash, doc.original_hash, doc.classification, chunk.text))
                combined = "\n".join(e.text for e in evidence)
                inspect_text(combined, self.limits.context_chars)
                disclosure_gate(combined, self.limits.context_chars)
                # Restricted records can be locally read, but never sent to a provider.
                if any(e.classification == "restricted" for e in evidence):
                    raise ControlError("provider_class_denied")
                self.store.audit(session, state, actor, request_id, "retrieve", "authorized",
                                 [e.chunk_id for e in evidence])
                return tuple(evidence), state.corpus_version
        except ControlError:
            if mismatch_id:
                with self.store.locked() as (session, state):
                    doc = self.store.document(mismatch_id, session)
                    doc.status = "quarantined"
                    doc.access_version += 1
                    state.corpus_version += 1
                    self.store.audit(session, state, actor, request_id, "integrity", "quarantined", [doc.id])
            raise
        except Exception:
            raise ControlError("retrieval_unavailable", "unavailable") from None
