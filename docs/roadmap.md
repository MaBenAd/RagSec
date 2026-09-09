# Implementation roadmap

All firewall milestones below are pending.

1. **Reproducible baseline:** freeze model, corpus and application versions; create a smoke run and synthetic benign/adversarial fixtures; record baseline results without new protections.
2. **Gateway and scanners:** unify REST/SSE decisions; establish authenticated actor context; add deterministic limits, normalized inspection and typed refusals. Verify fail-closed failure cases.
3. **RAG ingestion and retrieval:** isolate parsing; preserve hashes and provenance; quarantine suspicious documents; enforce access filters on every retrieved chunk. Test cross-user access and deletion.
4. **Bounded agent and policies:** introduce LangGraph with mock tools; integrate OPA for tool, data and memory operations. Require explicit grants and test denied arguments, timeouts and malformed decisions.
5. **Output and cache enforcement:** validate before release; test split secrets across streaming chunks; scope caches and invalidate after policy/corpus changes.
6. **Benchmark and reporting:** implement the paired-run harness, held-out evaluation, deterministic success oracles, per-category rates and latency distributions. Publish measured results with manifests and failure traces.
7. **Optional classifier comparison:** evaluate classifier-assisted scanning against deterministic defenses using ablations, false positives and added latency. Keep authorization independent.

A milestone is complete only when its implementation, tests and documentation agree. Scaffold files and deny-all policies alone do not satisfy integration milestones.
