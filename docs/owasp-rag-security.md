# OWASP reference and control backlog

Primary reference: [OWASP RAG Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/RAG_Security_Cheat_Sheet.html), consulted 2026-09-09. This is the initial control reference, not a live threat-intelligence feed or certification.

The following is RagSec's proposed implementation mapping, not a claim of completed controls.

| OWASP section | RagSec work item |
|---|---|
| 1 Document Poisoning | Ingestion provenance and quarantine tests |
| 2 Embedding Manipulation | Index permissions and later anomaly experiments |
| 3 Context Window Attacks | Per-source context budgets |
| 4 Access Control Inheritance | Chunk permissions and deletion propagation |
| 5 Source Attribution and Provenance | Answer-to-source evidence |
| 6 Chunk Isolation | Scope-aware retrieval tests |
| 7 Index Integrity | Versioned corpus manifests |
| 8 Query Injection via Retrieval | Normalized query inspection |
| 9 Output Validation and Enforcement | Validation before response release |
| 10 Tool Invocation and Agent Safety | Host-enforced Rego decisions |
| 11 Caching Risks | Permission-aware cache isolation |
| 12 Monitoring and Incident Response | Redacted decision traces and replay |
| 13 Supply Chain Risk in Ingestion | Bounded parser environments |
| 14 Fail-Closed Design | Outage and malformed-response tests |

Track each implemented control with its test, version and measured limitations. Tool-memory scenarios extend this RAG reference to the agent architecture requested for RagSec.

## Execution references

The [roadmap](roadmap.md) defines milestone dependencies. The [project checklist](project-todo.md) supplies repository-specific implementation and acceptance tasks. All references below are pending work, not evidence of enforcement.

| Section | Checklist task IDs |
|---|---|
| 1 | P3.1–P3.4 |
| 2 | P3.5, P7.2, P9.2 |
| 3 | P2.2, P4.3 |
| 4 | P0.3, P1.2–P1.3, P4.1, P5.3–P5.4 |
| 5 | P4.2, P5.1 |
| 6 | P3.5, P4.1 |
| 7 | P3.4–P3.5, P7.2–P7.3 |
| 8 | P2.2, P2.5, P4.1 |
| 9 | P2.4, P4.4, P5.1, P5.5 |
| 10 | P6.1–P6.3 |
| 11 | P5.2–P5.4 |
| 12 | P7.1–P7.3, P8.1–P8.4 |
| 13 | P3.2–P3.3, P7.5 |
| 14 | P1.3, P2.1–P2.5, P4.5, P5.2, P7.4 |

RagSec-specific extensions: P6.4 covers persistent memory; P6.5 covers agent benchmark parity; P8.5 covers product handoff. Optional research in P9 is not a prerequisite for deterministic enforcement.
