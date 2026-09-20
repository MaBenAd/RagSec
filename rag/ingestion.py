import json
from pathlib import Path
from sqlalchemy import select, delete

from gateway.contracts import DocumentUpload, Resource
from gateway.errors import ControlError
from rag.models import Chunk, Document, Source, Tombstone
from rag.store import digest, new_id, resource
from rag.vectors import EMBEDDING_VERSION
from scanners.inspection import inspect_text


class Ingestion:
    def __init__(self, store, policy, writer, staging_root=None):
        self.store, self.policy, self.writer = store, policy, writer
        self.staging_root = Path(staging_root) if staging_root else None

    def register_source(self, actor, source_id):
        target = Resource(id=source_id, tenant=actor.tenant, owner=actor.id,
                          classification="public", status="staged", version=1, access_version=1)
        with self.store.locked() as (session, state):
            self.store.current(actor, session)
            self.policy.require(actor, "manage", target)
            existing = session.get(Source, source_id)
            if existing and existing.tenant != actor.tenant:
                raise ControlError("source_unavailable")
            if not existing:
                session.add(Source(id=source_id, tenant=actor.tenant, registered_by=actor.id, enabled=True))
            self.store.audit(session, state, actor, new_id(), "source", "registered", [source_id])

    def stage(self, actor, upload: DocumentUpload, *, original: bytes | None = None,
              parser_version="plain-text-v1", original_path=None):
        inspected = inspect_text(upload.text)
        original_hash = digest(original if original is not None else upload.text)
        with self.store.locked() as (session, state):
            self.store.current(actor, session)
            target = Resource(id=upload.source_id, tenant=actor.tenant, owner=actor.id,
                              classification=upload.classification, status="staged", version=1, access_version=1)
            self.policy.require(actor, "ingest", target)
            source = session.get(Source, upload.source_id)
            if not source or not source.enabled or source.tenant != actor.tenant:
                raise ControlError("source_unregistered")
            if session.scalar(select(Tombstone).where(Tombstone.tenant == actor.tenant,
                                                     Tombstone.original_hash == original_hash)):
                raise ControlError("source_tombstoned")
            duplicate = session.scalar(select(Document).where(
                Document.tenant == actor.tenant, Document.owner == actor.id, Document.source_id == source.id,
                Document.original_hash == original_hash, Document.classification == upload.classification))
            if duplicate:
                return duplicate.id
            doc = Document(id=new_id(), tenant=actor.tenant, owner=actor.id, source_id=source.id,
                           classification=upload.classification, status="staged", version=1, access_version=1,
                           original_hash=original_hash, extraction_hash=digest(upload.text), text=upload.text,
                           original_path=original_path, parser_version=parser_version,
                           embedding_version=EMBEDDING_VERSION, signals_json=json.dumps(inspected.signals),
                           created_at=self.store.clock())
            if original is not None and self.staging_root:
                import os
                self.staging_root.mkdir(parents=True, exist_ok=True, mode=0o700)
                target = self.staging_root / f"{doc.id}.pdf"
                descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(original)
                doc.original_path = str(target)
            session.add(doc)
            self.store.audit(session, state, actor, new_id(), "ingest", "staged", [doc.id])
            # Scan and stage occur in one transaction; searchable publication is separate.
            doc.status = "quarantined" if inspected.signals else "scanned"
            self.store.audit(session, state, actor, new_id(), "scan", doc.status, [doc.id])
            return doc.id

    def review(self, actor, doc_id, version, approve):
        with self.store.locked() as (session, state):
            self.store.current(actor, session)
            doc = self.store.document(doc_id, session)
            self.policy.require(actor, "approve", resource(doc))
            if doc.version != version or doc.status not in {"scanned", "quarantined"}:
                raise ControlError("invalid_transition")
            doc.status = "approved" if approve else "quarantined"
            doc.reviewer, doc.reviewed_at = actor.id, self.store.clock()
            self.store.audit(session, state, actor, new_id(), "review", doc.status, [doc.id])

    @staticmethod
    def payload(doc, chunk):
        return {"chunk_id": chunk.id, "document_id": doc.id, "tenant": doc.tenant,
                "owner": doc.owner, "classification": doc.classification, "version": doc.version,
                "access_version": doc.access_version, "text": chunk.text,
                "content_hash": chunk.content_hash, "embedding_version": doc.embedding_version}

    def publish(self, actor):
        with self.store.locked() as (session, state):
            self.store.current(actor, session)
            self.policy.require(actor, "publish", Resource(id="corpus", tenant=actor.tenant, owner=actor.id,
                                classification="public", status="approved", version=1, access_version=1))
            docs = session.scalars(select(Document).where(Document.tenant == actor.tenant,
                                  Document.status.in_(["approved", "indexed"]))).all()
            records = []
            for doc in docs:
                if session.get(Tombstone, doc.id) or (doc.expires_at and doc.expires_at <= self.store.clock()):
                    continue
                if digest(doc.text) != doc.extraction_hash:
                    raise ControlError("manifest_mismatch")
                chunks = session.scalars(select(Chunk).where(Chunk.document_id == doc.id)).all()
                if not chunks:
                    chunks = [Chunk(id=new_id(), document_id=doc.id, version=doc.version,
                                    text=doc.text[i:i+2000], content_hash=digest(doc.text[i:i+2000]))
                              for i in range(0, len(doc.text), 2000)]
                    session.add_all(chunks)
                records.extend(self.payload(doc, chunk) for chunk in chunks)
            collection = f"rs_{actor.tenant}_{new_id()}"
            # Failure leaves the committed active pointer and prior corpus intact.
            self.writer.build(collection, records)
            collections = json.loads(state.collections_json)
            collections[actor.tenant] = collection
            state.collections_json = json.dumps(collections)
            state.corpus_version += 1
            for doc in docs:
                if not session.get(Tombstone, doc.id):
                    doc.status = "indexed"
            self.store.audit(session, state, actor, new_id(), "index", "published", [d.id for d in docs])
            return collection

    def revoke(self, actor, doc_id):
        with self.store.locked() as (session, state):
            self.store.current(actor, session)
            doc = session.get(Document, doc_id)
            if not doc:
                raise ControlError("resource_unavailable")
            self.policy.require(actor, "delete", resource(doc))
            if not session.get(Tombstone, doc_id):
                session.add(Tombstone(document_id=doc_id, original_hash=doc.original_hash,
                                      tenant=doc.tenant, revoked_at=self.store.clock(), cleaned=False))
                doc.status, doc.access_version = "revoked", doc.access_version + 1
                state.corpus_version += 1
                self.store.audit(session, state, actor, new_id(), "revoke", "revoked", [doc.id])

    def cleanup(self):
        """Idempotent worker: DB denial commits before best-effort physical removal."""
        with self.store.locked() as (session, _state):
            from rag.models import Memory
            session.execute(delete(Memory).where(Memory.expires_at <= self.store.clock()))
            for tombstone in session.scalars(select(Tombstone).where(Tombstone.cleaned == False)):
                for collection in self.writer.collections():
                    self.writer.delete_document(collection, tombstone.document_id)
                doc = session.get(Document, tombstone.document_id)
                if doc:
                    # Original files live under generated IDs in a configured staging root.
                    if doc.original_path:
                        Path(doc.original_path).unlink(missing_ok=True)
                    doc.text, doc.status, doc.original_path = "", "deleted", None
                session.execute(delete(Chunk).where(Chunk.document_id == tombstone.document_id))
                from backend.services.db_service import Message
                # Answers are derived artifacts too. Preserve only a safe tombstone message.
                for message in session.scalars(select(Message).where(Message.role == "assistant")):
                    metadata = json.loads(message.metadata_json or "{}")
                    if any(ref.get("document_id") == tombstone.document_id for ref in metadata.get("dependencies", [])):
                        message.content = "Source deleted."
                        message.metadata_json = "{}"
                tombstone.cleaned = True
            if self.staging_root:
                known = set(session.scalars(select(Document.original_path).where(Document.original_path.is_not(None))))
                # Only generated filenames within the staging directory are eligible.
                for path in self.staging_root.glob("*.pdf"):
                    if len(path.stem) == 32 and all(c in "0123456789abcdef" for c in path.stem) and str(path) not in known:
                        path.unlink()

    def integrity(self):
        findings = []
        with self.store.sessions() as session:
            from rag.models import SecurityState
            state = session.get(SecurityState, 1)
            for tenant, collection in json.loads(state.collections_json).items():
                actual = {r.get("chunk_id"): r for r in self.writer.records(collection)}
                expected = {}
                for chunk, doc in session.execute(select(Chunk, Document).join(
                        Document, Chunk.document_id == Document.id).where(
                            Document.tenant == tenant, Document.status == "indexed")):
                    if not session.get(Tombstone, doc.id):
                        expected[chunk.id] = self.payload(doc, chunk)
                for key in set(actual) | set(expected):
                    if actual.get(key) != expected.get(key):
                        findings.append({"tenant": tenant, "chunk_id": key, "reason": "index_mismatch"})
        return findings
