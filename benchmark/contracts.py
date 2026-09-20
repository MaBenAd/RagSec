from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    id: str
    category: str
    language: Literal["en", "fr", "ar"]
    partition: Literal["development", "heldout"]
    kind: Literal["attack", "benign"]
    scenario: Literal["answer", "poison", "cross_scope", "tool", "memory", "flood", "citation"]
    query: str
    preconditions: str
    authorized_behavior: str
    oracle: Literal["synthetic_canary", "executed_tool", "library_hours", "fabricated_citation"]


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    experiment: Literal["offline-control-ablation-v1"] = "offline-control-ablation-v1"
    revision: str
    source_tree_sha256: str
    corpus_sha256: str
    policy_sha256: str
    provider: Literal["adversarial-double-v1"] = "adversarial-double-v1"
    repetitions: int = Field(ge=1)
    seed: int
    python: str
    dependencies: dict[str, str]
    started_at: str
    cache_modes: list[str]
    limitations: list[str]
