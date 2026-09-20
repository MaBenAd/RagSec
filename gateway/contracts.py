"""Strict boundary contracts; none of the actor fields come from chat JSON."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Identifier = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class Actor(Contract):
    id: int = Field(gt=0)
    tenant: Identifier
    role: Literal["member", "admin"]
    enabled: bool
    access_version: int = Field(ge=1)
    session_version: int = Field(default=1, ge=1)
    grants: tuple[str, ...]


class Resource(Contract):
    id: Identifier
    tenant: Identifier
    owner: int = Field(gt=0)
    classification: Literal["public", "private", "restricted"]
    status: str
    version: int = Field(ge=1)
    access_version: int = Field(ge=1)


class ChatRequest(Contract):
    question: str = Field(min_length=1, max_length=4096)
    conversation_id: int | None = Field(default=None, gt=0)
    language: Literal["fr", "en", "ar"] = "fr"


class ToolCall(Contract):
    name: Literal["document_summary"]
    document_id: Identifier


class Candidate(Contract):
    answer: str = Field(max_length=8192)
    source_ids: tuple[Identifier, ...] = ()
    tool: ToolCall | None = None


class Citation(Contract):
    document_id: Identifier
    chunk_id: Identifier
    version: int
    document_hash: str
    chunk_hash: str
    token: str


class Outcome(Contract):
    request_id: Identifier
    status: Literal["allowed", "blocked", "unavailable", "no_evidence", "limited"]
    answer: str
    reason: str
    policy_version: str
    corpus_version: int
    access_version: int
    citations: tuple[Citation, ...] = ()
    conversation_id: int | None = None


class DocumentUpload(Contract):
    source_id: Identifier
    classification: Literal["public", "private", "restricted"]
    text: str = Field(min_length=1, max_length=32768)


class Review(Contract):
    version: int = Field(ge=1)
    approve: bool


class MemoryWrite(Contract):
    text: str = Field(min_length=1, max_length=2048)
    ttl_seconds: int = Field(ge=60, le=86400 * 30, default=3600)
