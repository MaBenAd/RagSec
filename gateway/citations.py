import base64
import hashlib
import hmac
import json
import time

from gateway.contracts import Citation
from gateway.errors import ControlError
from rag.store import digest, resource


class Citations:
    def __init__(self, keys: dict[str, bytes], active="v1", clock=time.time):
        if active not in keys or any(len(key) < 32 for key in keys.values()):
            raise ValueError("citation key configuration")
        self.keys, self.active, self.clock = keys, active, clock

    def sign(self, actor, evidence, answer, corpus_version):
        claims = {"kid": self.active, "actor": actor.id, "tenant": actor.tenant,
                  "access": actor.access_version, "corpus": corpus_version,
                  "document": evidence.document_id, "chunk": evidence.chunk_id,
                  "version": evidence.version, "document_hash": evidence.document_hash,
                  "chunk_hash": evidence.content_hash, "answer_hash": digest(answer),
                  "exp": int(self.clock()) + 300}
        payload = base64.urlsafe_b64encode(json.dumps(claims, sort_keys=True, separators=(",", ":")).encode()).decode().rstrip("=")
        signature = hmac.new(self.keys[self.active], payload.encode(), hashlib.sha256).hexdigest()
        return Citation(document_id=evidence.document_id, chunk_id=evidence.chunk_id,
                        version=evidence.version, document_hash=evidence.document_hash,
                        chunk_hash=evidence.content_hash, token=f"{payload}.{signature}")

    def verify(self, token, actor, store, policy, answer_hash=None):
        try:
            if len(token) > 2048:
                raise ValueError()
            payload, signature = token.split(".")
            claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
            expected = hmac.new(self.keys[claims["kid"]], payload.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError()
            if (claims["actor"] != actor.id or claims["tenant"] != actor.tenant
                    or claims["access"] != actor.access_version or claims["exp"] <= self.clock()
                    or (answer_hash is not None and answer_hash != claims["answer_hash"])):
                raise ValueError()
            from rag.models import Chunk
            with store.locked() as (session, state):
                store.current(actor, session)
                doc = store.document(claims["document"], session)
                policy.require(actor, "cite", resource(doc))
                chunk = session.get(Chunk, claims["chunk"])
                if (claims["corpus"] != state.corpus_version or not chunk or chunk.document_id != doc.id
                        or doc.version != claims["version"] or doc.original_hash != claims["document_hash"]
                        or chunk.content_hash != claims["chunk_hash"] or digest(chunk.text) != chunk.content_hash):
                    raise ValueError()
                return {"valid": True, "document_id": doc.id, "version": doc.version,
                        "document_hash": doc.original_hash, "chunk_hash": chunk.content_hash,
                        "answer_hash": claims["answer_hash"], "source_id": doc.source_id}
        except (ValueError, KeyError, TypeError, UnicodeError, ControlError):
            raise ControlError("citation_invalid") from None
