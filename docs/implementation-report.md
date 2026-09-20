# RagSec implementation report

Updated 2026-09-20. This report describes the implemented protected lab and its evidence. The inherited `backend/` application remains the comparison baseline and is not silently converted into the protected gateway.

## Delivered behavior

The protected FastAPI application is wired through `gateway/runtime.py`. `gateway/pipeline.py` is the shared REST/SSE path: it loads server-owned identity and current membership, applies request and actor budgets, normalizes bounded input, retrieves only policy-authorized evidence, assembles delimited untrusted context, invokes a bounded LangGraph graph, authorizes each mock tool call immediately before execution, validates structured output and citations, then rechecks access, corpus and source hashes while holding the final database lock. Disconnects cancel the active graph and no partial answer is emitted.

Ingestion is separate from querying. `rag/ingestion.py` records source, uploader, hashes, versions, classification, review decision, parser and embedding versions, and transitions through staged, scanned, quarantined, approved, indexed, revoked and deleted states. Qdrant is written only by `rag/worker.py` using a write key; the gateway uses a read key. `rag/retrieval.py` verifies SQL manifests and chunk hashes after the vector query. A mismatch quarantines the document. Revocation commits before asynchronous cleanup and invalidates cache dependencies.

The parser is a separate credential-free container with `network_mode: none`, a read-only filesystem, non-root UID, CPU/address-space/file limits, generated staging paths and a subprocess resource ceiling. The gateway and worker containers are non-root, capability-dropped, read-only, resource-limited, and attached to an internal data network; only the gateway is published to loopback.

The browser has a dedicated protected lab at `/secure` and `/secure/admin`. It uses session storage for the protected token, explicit blocked/unavailable/no-evidence states, source verification actions, safe link protocols, inert image rendering, French/English/Arabic text, and RTL layout. Existing baseline screens remain available for comparison.

## Evidence

The baseline suite passed 130 tests before the protected changes. With the local OPA/PostgreSQL/Qdrant integration services, the final combined suite passed 175 tests (`backend/tests/` plus `tests/`), including migration upgrade/downgrade/re-upgrade, parser isolation, session revocation, and a rejected Qdrant query-key write. The service-free repeat passes 173 tests and skips only the two integration cases. Rego strict check and 17 policy tests passed. The frontend production build passed on Next.js 15.5.25. A local Python audit completed with no known vulnerabilities for the pinned security environment; a later network-only audit attempt was unavailable because PyPI DNS was restricted. The frontend dependency audit completed with zero vulnerabilities after the dependency upgrades.

The frozen offline harness is under `benchmark/runner.py`, with contracts in `benchmark/contracts.py`, cases in `attacks/cases-v1.jsonl`, and an explicit manifest in `benchmark/frozen-v1.json`. A run uses three repetitions, cold and warm cache arms, randomized isolated subprocess order, a deterministic adversarial provider, exact canary/tool oracles, and descriptive Wilson intervals. It is not a live-model result.

The recorded offline run used 21 attack attempts and 9 benign attempts per mode/cache arm. Protected cold and warm arms released 0/21 attack objectives and completed 9/9 benign objectives, with 0 false positives and 0 availability failures. Baseline arms released 21/21 attack objectives. The output-validator ablation released 6/21, showing why output gating remains a mandatory control. The protected attack interval is descriptive (0 to 0.1546 Wilson 95% interval), not a production attack-success claim. This artifact was regenerated after the session-version migration; it is still an offline deterministic result, not a live-model or production guarantee.

## Roadmap completion record

P0 is complete for the local lab contract, baseline inventory, synthetic access matrix, fixture schemas, and tested limits. P1–P6 are implemented in `gateway/`, `rag/`, `scanners/`, `policies/`, and the protected migrations. P7 is implemented for local Compose, resource isolation, audit rows, integrity checks and restore reconciliation; external TLS, alert routing and provider retention remain deployment decisions. P8 is implemented for the offline matrix, paired harness, held-out case partition, evidence artifacts and product handoff; browser E2E remains an environment-dependent release check. P9 is intentionally partial: optional classifier, multi-model embedding experiments and recurring maintenance have not been claimed as completed protection.

## Known limitations and deferred work

The provider is offline and deterministic; no claim is made about resistance to arbitrary live models. Embedding monitoring and multi-model drift validation are not implemented. Embeddings are protected by service and chunk authorization, but encryption at rest and per-tenant keys depend on deployment storage configuration. TLS and external provider retention require an operator decision. The browser E2E test requires a running frontend/API and a valid lab admin password; its first run exposed a test environment login mismatch rather than an application assertion, so it remains a release check to rerun after the protected service is provisioned with the same password.

The baseline routes are intentionally not advertised as protected. Use the protected Compose profile and `/secure` surface when evaluating RagSec controls.
