# OWASP RAG Security assessment

Assessment date: 2026-09-20. Reference: [OWASP RAG Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/RAG_Security_Cheat_Sheet.html). This is an engineering evidence review, not OWASP certification.

| OWASP area | Implemented evidence | Assessment |
|---|---|---|
| Document poisoning | SHA-256 source/extraction/chunk hashes, source allowlist, scan/quarantine/review workflow, retrieval hash recheck, quarantine on mismatch | Implemented for the protected lab |
| Embedding manipulation/privacy | Version recorded, bounded top-k and relevance threshold, Qdrant credential separation | Partial; distribution drift, multi-model checks, encryption-at-rest and privacy noise remain deployment/research work |
| Context-window attacks | NFKC/invisible/percent/base64 normalization, bounded query/history/chunks/context, explicit untrusted delimiters and final system reinforcement | Implemented and tested offline |
| Access-control inheritance | Membership and grants are server-owned; classification, tenant, owner, version and access version are copied into every chunk; OPA checks precede provider input | Implemented and tested |
| Deletion/retention | Revocation tombstones, corpus/cache invalidation, chunk/vector/message cleanup, expiry cleanup and restore reconciliation | Implemented for lab lifecycle; backup retention still operator-owned |
| Provenance/citations | Signed HMAC citation envelopes bind actor, scope, corpus, answer digest, document/chunk hashes and expiry; verification reauthorizes current records | Implemented and tested |
| Chunk isolation | Pre-query tenant/classification filter plus authoritative post-query verification | Implemented and tested; production encryption is deployment-dependent |
| Index integrity | Staged versioned collections, manifest equality before active pointer swap, Qdrant writer/query keys, periodic integrity worker and snapshots as deployment volume capability | Implemented for the lab; anomaly thresholds and snapshot drill need operations evidence |
| Retrieval query abuse | Normalization, injection signals, actor request/token budgets, bounded top-k and no score disclosure | Implemented; reconnaissance analytics are not yet a tuned detection model |
| Output validation | Structured Pydantic candidate, allowed source IDs, sensitive-data and unsafe-markup gate, buffered REST/SSE release, cross-chunk secret test | Implemented and tested |
| Tool/agent safety | LangGraph step/time/tool budgets, strict tool schema, immediate OPA authorization, synthetic read-only tool, zero-side-effect denial tests | Implemented for the mock tool; consequential tools and confirmation UX remain disabled |
| Caching | HMAC cache envelope, actor/tenant/access/corpus/policy/prompt/model key, public-only caching, TTL, dependency invalidation, release recheck | Implemented and tested |
| Monitoring/incident response | Opaque request/actor/stage/reason/resource audit rows, integrity worker, recovery export/reconcile functions, benchmark red-team cases | Implemented for lab evidence; alert routing and a rehearsed operator drill remain |
| Ingestion supply chain | Pinned/hashes, parser isolation, source registration, staged review and no external connectors | Implemented for local sources; connector vetting is deferred because connectors are disabled |
| Fail-closed design | OPA errors, retrieval errors, malformed manifests, cache failures, provider failures, output/citation failures and disconnects produce typed denial/unavailability with no model-only fallback | Implemented and tested |

## Verdict

The protected lab substantially follows the OWASP RAG Security Cheat Sheet’s foundational and next-priority controls. It should be described as OWASP-aligned in the tested lab scope, not as fully compliant or certified. The principal remaining gaps are operational: TLS and provider-retention decisions, encrypted vector storage, embedding drift/multi-model monitoring, alert ownership, snapshot/restore rehearsal, external connector governance, and live-model held-out evaluation. The inherited baseline app is not OWASP-aligned as a complete RAG firewall because its routes are not connected to this protected pipeline.
