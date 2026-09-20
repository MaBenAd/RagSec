"""Security records use the existing application database and migration chain."""
from sqlalchemy import Boolean, Column, Float, Integer, String, Text, UniqueConstraint
from backend.services.db_service import Base


class Membership(Base):
    __tablename__ = "security_memberships"
    user_id = Column(Integer, primary_key=True)
    tenant = Column(String(64), nullable=False)
    role = Column(String(16), nullable=False, default="member")
    enabled = Column(Boolean, nullable=False, default=True)
    access_version = Column(Integer, nullable=False, default=1)
    session_version = Column(Integer, nullable=False, default=1)
    grants_json = Column(Text, nullable=False)


class SecurityState(Base):
    __tablename__ = "security_state"
    id = Column(Integer, primary_key=True)
    corpus_version = Column(Integer, nullable=False, default=1)
    collections_json = Column(Text, nullable=False, default="{}")


class Source(Base):
    __tablename__ = "security_sources"
    id = Column(String(64), primary_key=True)
    tenant = Column(String(64), nullable=False)
    registered_by = Column(Integer, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)


class Document(Base):
    __tablename__ = "security_documents"
    id = Column(String(64), primary_key=True)
    tenant = Column(String(64), nullable=False, index=True)
    owner = Column(Integer, nullable=False)
    source_id = Column(String(64), nullable=False)
    classification = Column(String(16), nullable=False)
    status = Column(String(16), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    access_version = Column(Integer, nullable=False, default=1)
    original_hash = Column(String(64), nullable=False)
    extraction_hash = Column(String(64), nullable=False)
    text = Column(Text, nullable=False)
    original_path = Column(Text, nullable=True)
    parser_version = Column(String(64), nullable=False)
    embedding_version = Column(String(64), nullable=False)
    signals_json = Column(Text, nullable=False)
    reviewer = Column(Integer, nullable=True)
    reviewed_at = Column(Float, nullable=True)
    created_at = Column(Float, nullable=False)
    expires_at = Column(Float, nullable=True)
    __table_args__ = (UniqueConstraint("tenant", "owner", "source_id", "original_hash", "classification"),)


class Chunk(Base):
    __tablename__ = "security_chunks"
    id = Column(String(64), primary_key=True)
    document_id = Column(String(64), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False)


class Tombstone(Base):
    __tablename__ = "security_tombstones"
    document_id = Column(String(64), primary_key=True)
    original_hash = Column(String(64), nullable=False)
    tenant = Column(String(64), nullable=False)
    revoked_at = Column(Float, nullable=False)
    cleaned = Column(Boolean, nullable=False, default=False)


class Memory(Base):
    __tablename__ = "security_memory"
    id = Column(String(64), primary_key=True)
    tenant = Column(String(64), nullable=False)
    owner = Column(Integer, nullable=False)
    access_version = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False)
    provenance = Column(String(64), nullable=False)
    expires_at = Column(Float, nullable=False)


class Budget(Base):
    __tablename__ = "security_budgets"
    user_id = Column(Integer, primary_key=True)
    window = Column(Integer, nullable=False)
    requests = Column(Integer, nullable=False)
    tokens = Column(Integer, nullable=False)


class Audit(Base):
    __tablename__ = "security_audit"
    id = Column(String(64), primary_key=True)
    request_id = Column(String(64), nullable=False, index=True)
    actor_id = Column(Integer, nullable=False)
    stage = Column(String(32), nullable=False)
    reason = Column(String(64), nullable=False)
    resource_ids = Column(Text, nullable=False)
    policy_version = Column(String(32), nullable=False)
    corpus_version = Column(Integer, nullable=False)
    access_version = Column(Integer, nullable=False)
    duration_ms = Column(Float, nullable=False)
    created_at = Column(Float, nullable=False)
