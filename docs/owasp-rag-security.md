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
