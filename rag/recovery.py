"""Restore a snapshot only after overlaying a separately retained control export.

Operator must supply the newest export from outside the restored backup. This
cannot discover deletions that the operator failed to retain; readiness alone
does not certify the age of an arbitrary restored database.
"""
import json
from sqlalchemy import select

from gateway.errors import ControlError
from rag.models import Document, Membership, Tombstone


def export_controls(store):
    with store.locked() as (session, _state):
        return {"schema_version": 1, "created_at": store.clock(),
                "memberships": [{"user_id": m.user_id, "tenant": m.tenant, "role": m.role,
                                 "enabled": m.enabled, "access_version": m.access_version,
                                 "session_version": m.session_version,
                                 "grants_json": m.grants_json} for m in session.scalars(select(Membership))],
                "tombstones": [{"document_id": t.document_id, "tenant": t.tenant,
                                "original_hash": t.original_hash, "revoked_at": t.revoked_at}
                               for t in session.scalars(select(Tombstone))]}


def reconcile_restore(store, controls):
    if controls.get("schema_version") != 1 or not all(k in controls for k in ["memberships", "tombstones"]):
        raise ControlError("restore_controls_missing")
    with store.locked() as (session, state):
        allowed = {m["user_id"]: m for m in controls["memberships"]}
        for membership in session.scalars(select(Membership)):
            latest = allowed.get(membership.user_id)
            if not latest:
                membership.enabled = False
                membership.access_version += 1
            else:
                for key in ["tenant", "role", "enabled", "access_version", "session_version", "grants_json"]:
                    setattr(membership, key, latest[key])
        for record in controls["tombstones"]:
            if not session.get(Tombstone, record["document_id"]):
                session.add(Tombstone(**record, cleaned=False))
            doc = session.get(Document, record["document_id"])
            if doc:
                doc.status = "revoked"
                doc.access_version += 1
        # Never reactivate a restored vector pointer. Explicit rebuild is required.
        state.collections_json = "{}"
        state.corpus_version += 1
