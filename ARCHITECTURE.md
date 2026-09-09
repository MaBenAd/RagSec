# RagSec architecture

Status: proposed firewall around the inherited Chatbot-USMS application. See [README](README.md) for the target flow and [threat model](THREAT_MODEL.md) for actual boundaries and assumptions.

## Baseline and integration seams

The current FastAPI routes call `backend/services/router_service.py`, structured timetable queries or `rag_service.py`, then `chatbot_service.py` / `groq_service.py`. The frontend consumes REST and SSE. PostgreSQL (SQLite in local fallback) stores users and conversations; Qdrant stores vectors; Redis provides caching. These paths are retained as the benchmark's comparison application.

Integrate security at both REST and streaming entry points through one shared decision pipeline. The inherited router classifies academic intent; it is not an authorization engine. Authentication establishes a server-owned actor context before any retrieval, cache lookup or model call. Never accept tenant or role claims from prompts.

## Planned components and contracts

| Component | Input and output | Enforcement responsibility |
|---|---|---|
| gateway/ | Authenticated request → allow, block or quarantine decision | Request IDs, schema validation, size limits, timeouts, consistent REST/SSE handling |
| scanners/ | Untrusted text → normalized view, findings and bounded risk signals | Direct/indirect injection signals, obfuscation checks and output inspection |
| rag/ | Documents → classified chunks; query → authorized context | Parser isolation, hashes, provenance, ACL inheritance, retrieval filters and context budgets |
| LangGraph agent | Authorized context → answer or proposed tool operation | Bounded steps and token budget; no direct execution privileges |
| policies/ | Server-owned actor/resource/action → explicit allow/deny | OPA decisions for each tool call, document access and memory operation |
| Output validator | Candidate response → validated release or refusal | Synthetic-secret/PII rules, source checks and safe rendering |
| benchmark/ | Versioned cases + run manifest → traces and aggregate results | Comparable protected/unprotected runs and reproducible scoring |

Suggested decision record: request ID, actor ID, action, resource ID, policy version, decision, reason codes, elapsed milliseconds and sanitized evidence references. Store sensitive payloads separately with restricted access; ordinary logs should not reproduce secrets or full documents.

## Document lifecycle

Untrusted PDF → bounded isolated parser → injection detection → trust classification / quarantine → approved chunks with provenance and access metadata → vector database → authorized retrieval → policy check → delimited context → LLM.

Retain original content hashes and scan versions so transformations remain auditable. A clean scan is not authority to grant access. Trust levels describe provenance, while authorization comes from server-controlled ownership and permissions. Re-evaluate permissions on retrieval, not just ingestion. Keep source IDs attached to each chunk and resulting citation.

## Tool and memory lifecycle

A model proposes an operation. The host validates its schema, derives actor identity from the session and asks OPA about the exact action, resource and arguments. Only an allowed decision reaches a sandboxed tool. Tool results re-enter as untrusted data. Start with mock read-only tools; add real capabilities only with explicit permissions and test coverage.

Memory is a separate data boundary: validate writes, bind ownership and source provenance, scope reads, enforce retention and allow revocation. Conversation text is not privileged persistent instruction. Policy timeout, malformed decision or missing metadata denies the operation.

## Output, streaming and failure handling

Validate before releasing bytes, including cross-chunk secret matches. Initially buffer complete candidate answers for validation; any later incremental design must prove equivalent enforcement. Refusals and policy errors use typed outcomes across REST/SSE. No fallback may bypass an unavailable mandatory scanner, authorization decision or output validator.

Cache keys must include actor/access scope, corpus version, policy version and relevant conversation context. Invalidate on document deletion or permission change. Do not reuse baseline cache behavior as a proven security control.

## Deployment choices

Keep Qdrant initially because the baseline already integrates it. Evaluate pgvector as an alternative only through measured retrieval and isolation tests. PostgreSQL holds provenance and audit records; Redis remains ephemeral. LangGraph and OPA are planned additions and are not dependencies or Compose services yet. Optional classifiers must have bounded timeouts and cannot override a deterministic denial.

Separate unprotected benchmark mode into an isolated test deployment. The normal gateway must not expose a client-selectable bypass flag. Use synthetic fixtures and local mock tools with no production credentials or external side effects.
