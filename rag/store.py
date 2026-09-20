import hashlib
import json
import time
import uuid
from contextlib import contextmanager

from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

from backend.services.db_service import User
from gateway.config import POLICY_VERSION
from gateway.contracts import Actor, Resource
from gateway.errors import ControlError
from rag.models import Audit, Budget, Document, Membership, SecurityState, Tombstone


def digest(text: str | bytes) -> str:
    return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()


def new_id() -> str:
    return uuid.uuid4().hex


def resource(doc: Document) -> Resource:
    return Resource(id=doc.id, tenant=doc.tenant, owner=doc.owner, classification=doc.classification,
                    status=doc.status, version=doc.version, access_version=doc.access_version)


class Store:
    def __init__(self, engine, clock=time.time):
        self.engine = engine
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False)
        self.clock = clock

    @contextmanager
    def locked(self):
        """All access mutations and final sends serialize on this database lock.

        PostgreSQL row lock works across workers; SQLite lab uses BEGIN IMMEDIATE.
        No lock is held while generating. No reliance on process-local mutexes.
        """
        with self.sessions() as session:
            try:
                if self.engine.dialect.name == "sqlite":
                    session.execute(text("BEGIN IMMEDIATE"))
                else:
                    session.execute(text("SET LOCAL lock_timeout = '2s'"))
                    session.execute(text("SET LOCAL statement_timeout = '5s'"))
                state = session.scalar(select(SecurityState).where(SecurityState.id == 1).with_for_update())
                if state is None:
                    raise ControlError("store_uninitialized", "unavailable")
                yield session, state
                session.commit()
            except BaseException:
                session.rollback()
                raise

    def actor(self, actor_id: int, session=None) -> Actor:
        if session is None:
            with self.sessions() as session:
                return self.actor(actor_id, session)
        member = session.get(Membership, actor_id)
        user = session.get(User, actor_id)
        if not member or not user or not member.enabled:
            raise ControlError("identity_disabled")
        # Role claims from an old JWT never confer current membership privileges.
        if member.role == "admin" and user.role != "admin":
            raise ControlError("role_revoked")
        return Actor(id=actor_id, tenant=member.tenant, role=member.role, enabled=member.enabled,
                     access_version=member.access_version, session_version=member.session_version,
                     grants=tuple(json.loads(member.grants_json)))

    def current(self, actor: Actor, session) -> None:
        if self.actor(actor.id, session) != actor:
            raise ControlError("access_changed")

    def document(self, doc_id: str, session) -> Document:
        doc = session.get(Document, doc_id)
        if (doc is None or session.get(Tombstone, doc_id) is not None
                or doc.status in {"revoked", "deleted"}
                or (doc.expires_at is not None and doc.expires_at <= self.clock())):
            raise ControlError("resource_unavailable")
        return doc

    def audit(self, session, state, actor, request_id, stage, reason, ids=(), duration=0):
        session.add(Audit(id=new_id(), request_id=request_id, actor_id=actor.id, stage=stage,
                          reason=reason, resource_ids=json.dumps(list(ids)), policy_version=POLICY_VERSION,
                          corpus_version=state.corpus_version, access_version=actor.access_version,
                          duration_ms=duration, created_at=self.clock()))

    def reserve(self, actor: Actor, limits):
        with self.locked() as (session, _state):
            self.current(actor, session)
            window = int(self.clock() // 60)
            budget = session.get(Budget, actor.id)
            if not budget:
                budget = Budget(user_id=actor.id, window=window, requests=0, tokens=0)
                session.add(budget)
            if budget.window != window:
                budget.window, budget.requests, budget.tokens = window, 0, 0
            # Reserve worst-case work, including retries, rather than trusting model usage.
            charge = (limits.context_chars + limits.history_chars + limits.query_chars
                      + limits.generation_tokens + 4096) * limits.attempts * (1 + limits.tool_steps)
            if (budget.requests >= limits.actor_requests_per_minute
                    or budget.tokens + charge > limits.actor_tokens_per_minute):
                raise ControlError("actor_budget", "limited")
            budget.requests += 1
            budget.tokens += charge
