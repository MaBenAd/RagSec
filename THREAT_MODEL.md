# RagSec threat model

## 1. Overview

RagSec is a planned AI/RAG security firewall built on Chatbot-USMS. This model separates inspected baseline behavior from the target architecture supplied by the project owner. It is an initial architecture model, not a vulnerability audit or proof of protection. Scope: the imported application, local/Docker workflows and proposed security boundaries. An independent read-only architecture pass informed this document.

| Component | Inspected source | Current behavior |
|---|---|---|
| Identity | `backend/services/auth_service.py:82` | JWT authentication and cookie/CSRF handling |
| Chat | `backend/routes/chat.py:86` | Authenticated requests with conversation ownership checks |
| Corpus administration | `backend/routes/admin.py:167` | Administrator uploads and rebuilds shared content |
| Retrieval | `backend/services/rag_service.py:1957` | Shared Qdrant context retrieval |
| Model boundary | `backend/services/groq_service.py:1495` | External generation with limited prompt guards |
| Persistence | `backend/services/db_service.py:47` | SQLAlchemy database configuration |
| Browser rendering | `frontend/src/components/chat/MessageBubble.tsx:88` | ReactMarkdown rendering without raw-HTML parsing at this call |

### Effective resources

| Deployment or workflow | Resource or capability | Configuration and precedence | Safe effective value or location | Readers, writers, or recipients | Enforcing control | Evidence or unknowns |
|---|---|---|---|---|---|---|
| Local/raw API | Application DB | DATABASE_URL or SQLite fallback | backend/data/users.db by default | Backend process | Application authorization; host filesystem permissions | `backend/services/db_service.py:24`, `backend/services/db_service.py:36` |
| Compose | PostgreSQL | DOCKER_DATABASE_URL supplies backend DATABASE_URL | postgres service; postgres_data volume | Backend / database | Host mapping is loopback; DB credentials from configuration | docker-compose.yml; URL and POSTGRES_* values must agree |
| Local ingestion | FAQ source files | Backend-relative FAQ directory | backend/data/faq/basename | Administrators write; retrieval reads | Admin dependency, basename normalization, allowed extensions and size limit | `backend/routes/admin.py:29`, `backend/routes/admin.py:167`, `backend/routes/admin.py:182` |
| Compose ingestion | FAQ files and application tree | Writable ./backend bind mount | /app/backend/data/faq maps to host backend/data/faq | Backend process and host operator | Application controls; no parser isolation established | docker-compose.yml; backend/Dockerfile |
| Raw API | Vector storage | QDRANT_URL wins; otherwise VECTORSTORE_PATH | backend/vectorstore_qdrant by default; faq_campus collection | Backend | Client/storage access; no tenant isolation established | `backend/services/rag_service.py:25`, `backend/services/rag_service.py:1127` |
| Development helpers | Vector service | Default QDRANT_URL set by scripts | http://127.0.0.1:6333 | Backend | Local service boundary | `dev.sh:109`, `dev.ps1:189` |
| Compose | Vector service | QDRANT_URL override | http://qdrant:6333; qdrant_data volume | Backend and internal network peers | Host port loopback; client API-key configuration not established | docker-compose.yml |
| Local/Compose | Answer cache | REDIS_HOST/REDIS_PORT; localhost fallback for default host | redis:6379 or 127.0.0.1:6379 | Backend/cache service | Cache may disable itself when unavailable | `backend/services/cache_service.py:11`, `backend/services/cache_service.py:24` |
| Local/Compose | Logs | Backend-relative path | backend/data/logs/app.log; mounted host directory in Compose | Backend/operator | Rotation and retention; not proof of redaction | `backend/services/logging_service.py:17`, `backend/services/logging_service.py:24` |
| Generation | External provider | Groq integration and configured key | Selected prompts, context and history leave the process | Model provider | Limited masking/classification and grounding | `backend/services/groq_service.py:1428`, `backend/services/groq_service.py:1510` |
| Browser | API requests and tokens | NEXT_PUBLIC_API_URL or client defaults | Local API defaults; build-time value needs verification in Docker | Browser/API | JWT plus browser script trust; localStorage token exists | `frontend/src/lib/api.ts:13`, `frontend/src/lib/api.ts:31`, `frontend/src/lib/api.ts:177` |
| Network startup | Public listeners | Helpers vs Compose port publishing | Helpers use loopback; Compose app ports bind without loopback restriction | Host/network clients | CORS/trusted hosts are application controls; TLS/firewall unknown | `dev.sh:132`, `backend/main.py:43`, docker-compose.yml |

## 2. Threat Model, Trust Boundaries, and Assumptions

### Assets and objectives

Protect private conversations, identity records, password hashes, provider credentials, corpus integrity, cache correctness, tool authority, audit records and service availability. Planned controls must prevent untrusted content from granting data, tool or memory privileges; prevent unauthorized retrieval before generation; and validate output before any bytes reach the caller.

### Actors and starting capabilities

An unauthenticated attacker can reach exposed public endpoints; an ordinary authenticated user controls prompts and their own conversation content. A document attacker needs an ingestion path: current uploads are administrator-only, so corpus poisoning assumes a malicious/compromised source accepted by an administrator or an explicitly added lower-trust ingestion feature. Administrators already possess corpus-management authority; exercising that permission is not itself an escalation. Model output and retrieved content are untrusted even when produced by normal workflows.

Attackers do not initially control trusted server configuration, policy bundles or host credentials. The planned multi-user access model must be specified before claiming tenant isolation: the present corpus is shared. No general agent tool-execution authority was established in the baseline review; tool-abuse scenarios apply when the planned agent is introduced.

### Existing controls and boundaries

JWT checks and conversation ownership protect application data (`backend/services/auth_service.py:100`, `backend/routes/chat.py:86`, `backend/routes/chat.py:216`). Administrator-only ingestion validates extensions, filenames and size (`backend/routes/admin.py:167`). Existing generation code includes heuristic checks, PII regex masking and an LLM injection classifier; classifier failure returns a non-injection outcome (`backend/services/groq_service.py:1428`, `backend/services/groq_service.py:1480`). History is appended separately (`backend/services/groq_service.py:1510`), so prompt masking cannot be assumed to cover all outgoing context.

The active answer cache uses exact hashed query keys, not semantic vector similarity (`backend/services/cache_service.py:51`, `backend/services/cache_service.py:84`). Chat cache keys use language and question with selected bypasses and no-history restrictions (`backend/routes/chat.py:95`, `backend/routes/chat.py:131`). Scope-aware RagSec caching is a planned enhancement, not an established guarantee.

Registration domain validation is not proof of mailbox ownership (`backend/routes/auth.py:117`). Authentication enrollment, role revocation and browser token storage need separate evaluation from prompt-injection defenses. CORS, rate limiting and masking do not establish compliance or a complete AI firewall.

### Planned invariants and unknowns

Server-authenticated identity must accompany each policy decision. Retrieved chunks inherit enforceable permissions; scan confidence never grants access. Model-proposed tools require host enforcement before execution. Memory reads/writes require ownership checks. Mandatory control failure denies the protected operation. Cache hits and SSE must pass equivalent enforcement. Context, parsing, tool steps and provider spend need bounded budgets.

Deployment TLS, live service exposure, actual provider retention, future policy schema and future tool permissions remain unresolved. New scanners, LangGraph, output validation and OPA are not integrated. Rego defaults are deny-all placeholders. Baseline operation is for an isolated development lab; no production assurance is claimed.

## 3. Attack Surface, Mitigations, and Attacker Stories

These are hypotheses and planned evaluation scenarios, not validated vulnerabilities.

| Priority | Scenario and capability gain | Prerequisites | Impact | Existing controls | Mitigation | Evidence |
|---|---|---|---|---|---|---|
| High | A user injects instructions to extract protected context | Protected data enters reachable model context | Confidentiality loss | Limited prompt guards, ownership checks | Scope retrieval, minimize context, validate outputs with synthetic-canary tests | groq_service.py references above; planned gateway/scanners |
| High | Poisoned documents influence answers or introduce indirect instructions | Administrator accepts attacker-influenced content | Answer integrity loss; possible extraction | Admin-only upload, filename/type/size checks | Isolated parsing, provenance, quarantine and retrieval-time policy | `backend/routes/admin.py:167`, `backend/services/rag_service.py:1957` |
| High | Model requests an unauthorized tool or manipulated arguments | Future tool integration grants host execution ability | Unauthorized side effect | No general tool executor established | Exact-action OPA authorization and sandboxed mock tools first | Planned ARCHITECTURE.md tool boundary |
| High | Cross-user data enters retrieval or a cached response | Future private documents or user-specific cached output | Unauthorized disclosure | Conversation ownership and cache bypasses | Actor/access-scope keys, permission filters and revocation tests | `backend/routes/chat.py:95`, `backend/services/cache_service.py:84` |
| High | Sensitive history reaches provider or output despite prompt masking | History contains synthetic protected data | Confidentiality loss | Prompt-focused masking | Whole-context data policy and output checks before release | `backend/services/groq_service.py:1510` |
| Medium | Memory injection persists hostile instructions | Future persistent agent memory | Integrity loss across turns | Stored conversation ownership; no dedicated memory policy | Provenance, scoped writes/reads and deletion | `backend/services/db_service.py:109`; planned memory policy |
| Medium | Flooding/encoded input evades inspection or exhausts budgets | Reachable prompts, upload or retrieval | Availability loss or attack evasion | Request limits, snippet truncation | Bounded decoding, token/chunk budgets, parser resource ceilings | `backend/routes/chat.py:76`, `backend/services/rag_service.py:2061` |
| High | Streaming releases protected bytes before final validation | Sensitive candidate output exists | Irrecoverable disclosure | Existing stream path; dedicated validator absent | Validate complete response first; test cross-chunk matches | `backend/routes/chat.py:145` |
| Medium | Parser, logs or deployment expose more host data than intended | Crafted accepted file, log access or exposed service | Depends on parser/runtime and deployment | Upload controls and loopback data-service ports | Parser sandbox, least-privilege mounts, redaction, deployment checks | docker-compose.yml; `backend/services/logging_service.py:24` |

Add paired benign cases for security-related questions so scanner blocking does not masquerade as robust defense. Benchmark each category with preconditions, outcome evidence and error accounting in benchmark/README.md.

## 4. Severity Calibration (Critical, High, Medium, Low)

- **Critical:** a demonstrated unauthenticated path to broad host execution or large-scale cross-user secret extraction. A hostile prompt or proposed tool call alone does not establish this impact.
- **High:** demonstrated unauthorized sensitive-data access or an executed privileged tool action. Tool hypotheses require an actual execution capability; that capability is not established in the baseline.
- **Medium:** bounded service disruption, persistent answer contamination or access to limited non-public metadata, with reachable prerequisites. A false factual answer alone is not equivalent to host compromise.
- **Low:** minor information exposure or narrow correctness issues without meaningful privilege gain. An authorized administrator publishing a document is normal authority, not automatically a vulnerability.

Confidence, prerequisites and impact must be reported separately. Policy stubs and source-based hypotheses are not runtime validation. Use owned fixtures and the benchmark to establish reproducible outcomes before assigning finding severity.
