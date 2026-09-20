"""Trusted local operator commands; never exposed through chat or agent tools."""
import argparse
import json
import os

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from backend.services import db_service
from gateway.contracts import DocumentUpload
from rag.models import Membership
from rag.store import Store


def migrate():
    cfg = Config(db_service.ALEMBIC_INI_PATH)
    cfg.set_main_option("script_location", "backend/alembic")
    cfg.set_main_option("sqlalchemy.url", db_service.DATABASE_URL.replace("%", "%%"))
    command.upgrade(cfg, "head")


def seed():
    password = os.environ.get("RAGSEC_DEMO_PASSWORD", "")
    if len(password) < 16:
        raise RuntimeError("Set RAGSEC_DEMO_PASSWORD to at least 16 characters")
    store = Store(db_service.engine)
    grants = ["read", "cite", "download", "tool", "memory_read", "memory_write", "memory_delete"]
    with store.locked() as (session, _):
        for name, tenant, role in [("alice", "alpha", "member"), ("bob", "beta", "member"),
                                   ("admin", "alpha", "admin"), ("beta-admin", "beta", "admin")]:
            email = f"{name}@example.test"
            user = session.scalar(select(db_service.User).where(db_service.User.email == email))
            if user:
                continue
            user = db_service.User(email=email, password=db_service.hash_password(password),
                                   role="admin" if role == "admin" else "student", language="en")
            session.add(user)
            session.flush()
            session.add(Membership(user_id=user.id, tenant=tenant, role=role, enabled=True, access_version=1,
                                   grants_json=json.dumps(grants + (["ingest", "approve", "delete", "publish", "manage"] if role == "admin" else []))))
    print("Synthetic accounts provisioned; passwords were not printed.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["migrate", "seed", "disable-user"])
    parser.add_argument("--user-id", type=int)
    args = parser.parse_args()
    if args.operation == "migrate":
        migrate()
    elif args.operation == "seed":
        seed()
    else:
        if not args.user_id:
            parser.error("--user-id required")
        with Store(db_service.engine).locked() as (session, _state):
            member = session.get(Membership, args.user_id)
            if not member:
                parser.error("unknown user")
            member.enabled = False
            member.access_version += 1


if __name__ == "__main__":
    main()
