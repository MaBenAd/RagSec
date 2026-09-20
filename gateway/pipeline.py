"""One bounded graph, one final release gate for REST, SSE and cache hits."""
import asyncio
import json
import time
from dataclasses import dataclass
from typing import TypedDict

import httpx
from langgraph.graph import StateGraph, START, END
from sqlalchemy import select

from backend.services.db_service import Conversation, Message
from gateway.config import POLICY_VERSION
from gateway.contracts import Candidate, Outcome
from gateway.errors import ControlError
from gateway.provider import payload
from rag.store import new_id
from scanners.inspection import disclosure_gate, inspect_text, output_gate


class GraphState(TypedDict, total=False):
    actor: object
    request: object
    request_id: str
    history: list
    evidence: tuple
    corpus: int
    candidate: Candidate
    cache_key: str
    cache_hit: bool
    tool_result: str


@dataclass(frozen=True)
class Prepared:
    actor: object
    request: object
    outcome: Outcome
    evidence: tuple = ()
    candidate: Candidate | None = None
    cache_key: str = ""
    cache_hit: bool = False


class Pipeline:
    def __init__(self, store, policy, retrieval, provider, cache, citations, tools, limits):
        self.store, self.policy, self.retrieval, self.provider = store, policy, retrieval, provider
        self.cache, self.citations, self.tools, self.limits = cache, citations, tools, limits
        self.active = 0
        graph = StateGraph(GraphState)
        for name in ["retrieve", "generate", "propose_tool", "authorize", "execute", "validate"]:
            graph.add_node(name, getattr(self, "node_" + name))
        graph.add_edge(START, "retrieve")
        names = ["retrieve", "generate", "propose_tool", "authorize", "execute", "validate", END]
        for first, second in zip(names, names[1:]):
            graph.add_edge(first, second)
        self.graph = graph.compile()

    def history(self, actor, request):
        if request.conversation_id is None:
            return []
        with self.store.sessions() as session:
            conversation = session.get(Conversation, request.conversation_id)
            if not conversation or conversation.user_id != actor.id:
                raise ControlError("conversation_denied")
            messages = session.scalars(select(Message).where(Message.conversation_id == conversation.id)
                                       .order_by(Message.id.desc()).limit(5)).all()
            history = [{"role": m.role, "content": m.content} for m in reversed(messages)]
        # Historical assistant answers may depend on revoked sources: reauthorize them.
        with self.store.locked() as (session, _state):
            self.store.current(actor, session)
            for m in messages:
                if m.role == "assistant":
                    metadata = json.loads(m.metadata_json or "{}")
                    for ref in metadata.get("dependencies", []):
                        from rag.retrieval import Evidence
                        self.retrieval.verify(actor, Evidence(**ref), session)
        disclosure_gate(json.dumps(history, ensure_ascii=False), self.limits.history_chars)
        return history

    async def node_retrieve(self, state):
        evidence, corpus = await asyncio.to_thread(self.retrieval.retrieve, state["actor"],
                                                   state["request"].question, state["request_id"])
        if not evidence:
            raise ControlError("no_authorized_evidence", "no_evidence")
        key = self.cache.cache_key(state["actor"], state["request"].model_dump(), state["history"],
                                   corpus, self.provider.model)
        cached = await asyncio.to_thread(self.cache.get, key)
        candidate = Candidate.model_validate_json(json.dumps(cached)) if cached else None
        return {"evidence": evidence, "corpus": corpus, "cache_key": key,
                "cache_hit": candidate is not None, **({"candidate": candidate} if candidate else {})}

    async def generate(self, state, tool_result=None):
        messages = payload(state["request"].question, state["history"], state["evidence"], tool_result)
        disclosure_gate(json.dumps(messages, ensure_ascii=False),
                        self.limits.context_chars + self.limits.history_chars + self.limits.query_chars + 4096)
        for attempt in range(self.limits.attempts):
            try:
                return await self.provider.generate(messages, self.limits.generation_tokens)
            except (httpx.HTTPError, TimeoutError):
                if attempt + 1 == self.limits.attempts:
                    raise ControlError("provider_unavailable", "unavailable") from None

    async def node_generate(self, state):
        return {} if state["cache_hit"] else {"candidate": await self.generate(state)}

    async def node_propose_tool(self, state):
        candidate = state["candidate"]
        if not isinstance(candidate, Candidate):
            raise ControlError("provider_schema")
        if candidate.tool and (self.limits.tool_steps < 1 or state["cache_hit"]):
            raise ControlError("tool_budget")
        return {}

    async def node_authorize(self, state):
        if state["candidate"].tool:
            await asyncio.to_thread(self.tools.authorize, state["actor"], state["candidate"].tool, state["evidence"])
        return {}

    async def node_execute(self, state):
        if not state["candidate"].tool:
            return {}
        result = await asyncio.to_thread(self.tools.execute, state["actor"], state["candidate"].tool,
                                         state["evidence"], state["request_id"])
        candidate = await self.generate(state, result)
        if candidate.tool:
            raise ControlError("tool_budget")
        return {"candidate": candidate, "tool_result": result}

    def validate(self, candidate, evidence):
        if not isinstance(candidate, Candidate) or candidate.tool is not None or not candidate.answer.strip():
            raise ControlError("output_schema")
        allowed = {e.chunk_id for e in evidence}
        if not candidate.source_ids or not set(candidate.source_ids) <= allowed:
            raise ControlError("citation_fabricated")
        output_gate(candidate.answer, self.limits.output_chars)

    async def node_validate(self, state):
        self.validate(state["candidate"], state["evidence"])
        return {}

    def denied(self, actor, request, request_id, error):
        text = {
            "en": {"blocked": "Request blocked by security policy.", "unavailable": "A required service is unavailable.",
                   "no_evidence": "No authorized evidence is available.", "limited": "Request budget exceeded."},
            "fr": {"blocked": "Requête bloquée par la politique de sécurité.", "unavailable": "Un service requis est indisponible.",
                   "no_evidence": "Aucune source autorisée disponible.", "limited": "Limite de requêtes atteinte."},
            "ar": {"blocked": "تم حظر الطلب وفق سياسة الأمان.", "unavailable": "الخدمة المطلوبة غير متاحة.",
                   "no_evidence": "لا توجد مصادر مصرح بها.", "limited": "تم تجاوز حد الطلبات."},
        }
        return Prepared(actor, request, Outcome(request_id=request_id, status=error.status,
                        answer=text[request.language][error.status], reason=error.reason, policy_version=POLICY_VERSION,
                        corpus_version=0, access_version=actor.access_version))

    async def prepare(self, actor, request):
        request_id = new_id()
        if self.active >= self.limits.concurrency:
            return self.denied(actor, request, request_id, ControlError("concurrency", "limited"))
        self.active += 1
        try:
            async with asyncio.timeout(self.limits.total_seconds):
                if not request.question.strip():
                    raise ControlError("empty_question")
                inspected = inspect_text(request.question, self.limits.query_chars)
                disclosure_gate(request.question, self.limits.query_chars)
                request = request.model_copy(update={"question": inspected.normalized})
                # Detection is a signal. ACLs and output gates remain independent.
                await asyncio.to_thread(self.store.reserve, actor, self.limits)
                history = await asyncio.to_thread(self.history, actor, request)
                state = await self.graph.ainvoke({"actor": actor, "request": request,
                                                 "request_id": request_id, "history": history},
                                                {"recursion_limit": 8})
                candidate = state["candidate"]
                return Prepared(actor, request, Outcome(request_id=request_id, status="allowed", answer=candidate.answer,
                                reason="cache_validated" if state["cache_hit"] else "validated",
                                policy_version=POLICY_VERSION, corpus_version=state["corpus"],
                                access_version=actor.access_version), state["evidence"], candidate,
                                state["cache_key"], state["cache_hit"])
        except ControlError as exc:
            return self.denied(actor, request, request_id, exc)
        except TimeoutError:
            return self.denied(actor, request, request_id, ControlError("deadline", "unavailable"))
        except Exception:
            return self.denied(actor, request, request_id, ControlError("control_failure", "unavailable"))
        finally:
            self.active -= 1

    def release(self, prepared, session, state):
        from dataclasses import asdict
        actor, request, outcome = prepared.actor, prepared.request, prepared.outcome
        self.store.current(actor, session)
        if outcome.status == "allowed":
            if outcome.corpus_version != state.corpus_version:
                raise ControlError("corpus_changed")
            for evidence in prepared.evidence:
                self.retrieval.verify(actor, evidence, session)
            self.validate(prepared.candidate, prepared.evidence)
            citations = tuple(self.citations.sign(actor, e, outcome.answer, state.corpus_version)
                              for e in prepared.evidence if e.chunk_id in prepared.candidate.source_ids)
            for evidence in prepared.evidence:
                if evidence.chunk_id in prepared.candidate.source_ids:
                    from rag.store import resource
                    self.policy.require(actor, "cite", resource(self.store.document(evidence.document_id, session)))
            conversation = session.get(Conversation, request.conversation_id) if request.conversation_id else None
            if request.conversation_id and (not conversation or conversation.user_id != actor.id):
                raise ControlError("conversation_denied")
            if not conversation:
                conversation = Conversation(user_id=actor.id, title="RagSec conversation")
                session.add(conversation)
                session.flush()
            session.add(Message(conversation_id=conversation.id, role="user", content=request.question))
            session.add(Message(conversation_id=conversation.id, role="assistant", content=outcome.answer,
                                metadata_json=json.dumps({"dependencies": [asdict(e) for e in prepared.evidence],
                                                          "citations": [c.model_dump() for c in citations]})))
            outcome = outcome.model_copy(update={"citations": citations, "conversation_id": conversation.id})
            if all(e.classification == "public" for e in prepared.evidence):
                self.cache.put(prepared.cache_key, prepared.candidate, self.limits.cache_seconds,
                               [e.document_id for e in prepared.evidence])
        self.store.audit(session, state, actor, outcome.request_id, "release", outcome.reason,
                         [e.document_id for e in prepared.evidence])
        return outcome
