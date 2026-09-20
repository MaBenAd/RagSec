"""Authenticated cache records in a protected namespace; failures are misses."""
import hashlib
import hmac
import json
import time

from gateway.config import POLICY_VERSION, PROMPT_VERSION


class Cache:
    def __init__(self, key: bytes, redis=None, clock=time.time, local=False):
        self.key, self.redis, self.clock, self.local = key, redis, clock, local
        self.entries = {}

    def cache_key(self, actor, question, history, corpus, model):
        payload = json.dumps([actor.model_dump(mode="json"), question, history, corpus,
                              POLICY_VERSION, PROMPT_VERSION, model], sort_keys=True)
        return "ragsec:v1:" + hmac.new(self.key, payload.encode(), hashlib.sha256).hexdigest()

    def get(self, key):
        try:
            raw = self.entries.get(key) if self.local else self.redis.get(key) if self.redis else None
            if not raw or len(raw) > 65536:
                return None
            envelope = json.loads(raw)
            payload = envelope["payload"]
            mac = hmac.new(self.key, payload.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(mac, envelope["mac"]):
                return None
            entry = json.loads(payload)
            return entry["answer"] if entry["expires"] > self.clock() else None
        except Exception:
            return None

    def put(self, key, candidate, ttl, document_ids=()):
        payload = json.dumps({"answer": candidate.model_dump(mode="json"), "expires": self.clock() + ttl,
                              "document_ids": list(document_ids)})
        raw = json.dumps({"payload": payload, "mac": hmac.new(self.key, payload.encode(), hashlib.sha256).hexdigest()})
        try:
            if self.local:
                # Lab cache is bounded; Redis handles TTL reclamation in deployment.
                if len(self.entries) >= 256:
                    self.entries.clear()
                self.entries[key] = raw
            elif self.redis:
                self.redis.setex(key, ttl, raw)
        except Exception:
            pass

    def invalidate(self, document_id):
        """Optional eager cleanup; version binding already denies stale release."""
        try:
            keys = list(self.entries) if self.local else self.redis.scan_iter(match="ragsec:v1:*", count=100) if self.redis else []
            for key in keys:
                raw = self.entries.get(key) if self.local else self.redis.get(key)
                if raw and document_id in json.loads(json.loads(raw)["payload"]).get("document_ids", []):
                    if self.local:
                        self.entries.pop(key, None)
                    else:
                        self.redis.delete(key)
        except Exception:
            return False
        return True
