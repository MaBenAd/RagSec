# RagSec implementation roadmap

Updated 2026-09-09. **All implementation milestones below are pending.** The inherited application works as the comparison baseline; the new security directories and deny-all Rego files are scaffolds. This document defines delivery order, not delivered protection or measured results.

Use the [project checklist](project-todo.md) for individual tasks, implementation seams and acceptance evidence. Contributor rules remain in [AGENTS.md](../AGENTS.md). Read the [architecture](../ARCHITECTURE.md), [threat model](../THREAT_MODEL.md) and [benchmark protocol](../benchmark/README.md) before implementing a milestone.

## Reference and scope

Reviewed the [OWASP RAG Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/RAG_Security_Cheat_Sheet.html) on 2026-09-09. Its fourteen sections cover poisoning, embeddings, context, permissions, provenance, isolation, index integrity, query abuse, outputs, tools, caching, operations, ingestion dependencies and failure behavior. See the [section mapping](owasp-rag-security.md).

The milestones and technical choices below are RagSec-specific engineering proposals based on the local architecture. This is not a reproduction of the cheat sheet or a claim of certification. Agent memory extends the project's scope beyond basic retrieval.

## Delivery sequence

| Milestone / checklist IDs | Depends on | Deliverable in this repository | Exit gate |
|---|---|---|---|
| M0 — Baseline and scope / P0 | None | Reproducible Chatbot-USMS lab, synthetic fixtures, route inventory, written access model | Offline baseline run recorded; benchmark arms and resource ownership defined |
| M1 — Contracts and policy foundation / P1 | M0 | Typed actor/resource/decision contracts in `gateway/`, migrations, OPA adapter and tested data policy | Missing identity, stale grants and policy failures deny; permitted fixture operation succeeds |
| M2 — Shared request and release path / P2 | M1 | REST/SSE adapter, scanner interface, provider adapter and initial complete-answer validator | Every response branch uses the gate; denied requests release no candidate answer bytes |
| M3 — Corpus lifecycle / P3 | M1–M2 | Staged ingestion in `rag/`, bounded parser worker, authoritative metadata, repeatable index builds | Only approved fixture versions become searchable; corrupt or interrupted builds stay inactive |
| M4 — Authorized retrieval / P4 | M3 | Qdrant isolation, resource policy, context assembly and provider disclosure controls | Cross-scope fixture content never enters provider input; retrieval failures cannot invoke model-only fallback |
| M5 — Responses and revocation / P5 | M4 | Citation verification, scoped cache, deletion jobs and safe browser display | Revoked sources cannot be released from fresh requests, cache or in-flight generation |
| M6 — Agent and memory / P6 | M5 | Bounded LangGraph workflow, mock tools, tool and memory Rego integration | Denied operations have zero side effects; step exhaustion terminates; both benchmark arms have equivalent capabilities |
| M7 — Operations and deployment / P7 | M5; M6 for agent release | Redacted audit trail, alerts, authenticated services, recovery and deployment runbooks | Poisoning recovery and restore rehearsals pass without resurrecting revoked content |
| M8 — Evaluation and release / P8 | M0–M7 | Versioned paired harness, held-out report, frontend walkthrough, CI release checks | Offline gates pass; live results are reproducible and honestly report errors and uncertainty |
| M9 — Optional experiments / P9 | M8 | Classifier ablations, embedding experiments, optional pgvector comparison | Each adopted change has measured benefit, documented cost and unchanged authorization invariants |

First target: an isolated protected RAG demo through M5 with synthetic data. M6 adds agent capabilities; M7–M8 are required before describing the full project as release-ready. A passed lab milestone does not establish production assurance.

## Implementation decisions

- Keep Python/FastAPI and the existing Qdrant integration. Introduce adapters around baseline services so experiment mode can preserve inherited behavior. pgvector is an alternative experiment, not a second mandatory store.
- Define tenant and classification semantics before creating private corpora. Use server-owned fixture scopes initially; academic class labels and registration email domains do not establish tenant membership.
- Implement OPA data decisions before secure retrieval. Tool and memory rules follow with their executors. Neither unconnected deny-all stubs nor an always-denied happy path satisfy a milestone.
- Establish output gating in M2, before enabling protected generation. Buffer candidate answers for both transports; add citation and lifecycle checks in M5. Protected caching stays disabled until M5.
- Keep the unprotected comparison in a separate lab process with separate state. A client request cannot select baseline mode. New tools must exist in both experiment arms before comparing their defenses.
- Add offline tests with each change. Begin the fixture schema in M0 and build the harness incrementally; held-out live-model evaluation waits for M8.

## Release invariants and failure matrix

These are required future behaviors, not current guarantees.

| Situation | Required protected behavior | Evidence |
|---|---|---|
| Missing actor, unknown resource or OPA timeout/malformed response | Stop before resource access or side effect | Spy on retriever/executor; assert no call |
| Required scanner or output validator fails | Typed unavailable outcome; no candidate content released | Inject exceptions through REST and SSE |
| Retrieval service fails | End knowledge request with an error | Assert generation fallback was not called |
| Valid retrieval returns no authorized evidence | Typed no-evidence result without invented citations | Empty authorized corpus fixture |
| Document version or hash fails verification | Exclude/quarantine version; abort if required evidence cannot be established | Mutate fixture after indexing |
| Redis is unavailable | Fresh execution through all mandatory controls | Cold-path gate assertions; no stale cache response |
| Permissions change during generation | Recheck authoritative versions immediately before release | Pause generator, revoke, resume |
| Client disconnects or resource budget expires | Cancel work; no unchecked fallback or follow-on tools | Cancellation and timeout fixtures |

Complete each task only when source, tests and active documentation agree. Record commit, exact command, result and remaining limitations in the checklist. Record blockers rather than checking unfinished work. Policy changes require `opa check --strict policies/` and `opa test policies/ -v`; behavioral changes require relevant offline tests and baseline regression. Live-model outcomes remain separate from unit-test evidence.

## Remaining decisions

P0 must settle the fixture access matrix, release scope and initial resource budgets. P7 must settle deployment exposure, provider data handling and operational ownership. P8 must set empirical quality/latency thresholds before opening held-out results. The illustrative numbers in the README are neither targets nor measurements. No calendar estimate is assigned until staffing and these decisions are known.
