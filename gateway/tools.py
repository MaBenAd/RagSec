from gateway.errors import ControlError
from rag.store import resource
from scanners.inspection import disclosure_gate, inspect_text


class Tools:
    """Only a synthetic read-only capability; no shell, HTTP or real write tool."""
    def __init__(self, store, policy):
        self.store, self.policy = store, policy
        self.executions = 0

    def authorize(self, actor, call, evidence):
        if call.document_id not in {e.document_id for e in evidence}:
            raise ControlError("tool_resource_denied")
        with self.store.locked() as (session, _state):
            self.store.current(actor, session)
            doc = self.store.document(call.document_id, session)
            self.policy.require(actor, "tool", resource(doc), tool=call.name)

    def execute(self, actor, call, evidence, request_id):
        if call.document_id not in {e.document_id for e in evidence}:
            raise ControlError("tool_resource_denied")
        with self.store.locked() as (session, state):
            self.store.current(actor, session)
            doc = self.store.document(call.document_id, session)
            # Exact operation reauthorized immediately before its side-effect counter.
            self.policy.require(actor, "tool", resource(doc), tool=call.name)
            self.executions += 1
            result = doc.text[:1000]
            inspect_text(result, 1000)
            disclosure_gate(result, 1000)
            self.store.audit(session, state, actor, request_id, "tool", "executed", [doc.id])
            return result
