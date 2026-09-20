from sqlalchemy import select
from gateway.contracts import Resource
from gateway.errors import ControlError
from rag.models import Memory
from rag.store import digest, new_id
from scanners.inspection import disclosure_gate, inspect_text


class Memories:
    def __init__(self, store, policy):
        self.store, self.policy = store, policy

    @staticmethod
    def target(memory):
        return Resource(id=memory.id, tenant=memory.tenant, owner=memory.owner,
                        classification="private", status="active", version=1,
                        access_version=memory.access_version)

    def write(self, actor, body):
        scan = inspect_text(body.text, 2048)
        disclosure_gate(body.text, 2048)
        if scan.signals:
            raise ControlError("memory_instruction")
        with self.store.locked() as (session, state):
            self.store.current(actor, session)
            memory = Memory(id=new_id(), tenant=actor.tenant, owner=actor.id,
                            access_version=actor.access_version, text=body.text, content_hash=digest(body.text),
                            provenance="user-explicit", expires_at=self.store.clock() + body.ttl_seconds)
            self.policy.require(actor, "memory_write", self.target(memory))
            session.add(memory)
            self.store.audit(session, state, actor, new_id(), "memory", "written", [memory.id])
            return memory.id

    def operation(self, actor, memory_id, action="memory_read"):
        with self.store.locked() as (session, state):
            self.store.current(actor, session)
            memory = session.get(Memory, memory_id)
            if (not memory or memory.expires_at <= self.store.clock()
                    or (action != "memory_delete" and memory.access_version != actor.access_version)
                    or digest(memory.text) != memory.content_hash):
                raise ControlError("memory_unavailable")
            self.policy.require(actor, action, self.target(memory))
            result = memory.text
            if action == "memory_delete":
                session.delete(memory)
            self.store.audit(session, state, actor, new_id(), "memory", action, [memory.id])
            return result
