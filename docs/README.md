# RagSec documentation

The implemented protected lab is documented in [implementation report](implementation-report.md) and [OWASP assessment](owasp-assessment.md). The inherited reports under `base-project/` are retained for provenance and are not current RagSec security claims.

RagSec upgrades [Chatbot-USMS](https://github.com/ALLAKORI/Chatbot-USMS.git) into an AI/RAG security firewall research project.

- [Project README](../README.md): purpose, current status, stack and baseline startup.
- [Architecture](../ARCHITECTURE.md): target components, interfaces and trust enforcement.
- [Threat model](../THREAT_MODEL.md): inherited boundaries, protected controls, assumptions and remaining defenses.
- [Roadmap](roadmap.md): implementation milestones and completion criteria.
- [Project implementation checklist](project-todo.md): ordered tasks, repository integration points, dependencies and acceptance evidence from setup through maintenance.
- [Testing](testing.md): baseline regression, protected firewall validation and environment-dependent checks.
- [Benchmark protocol](../benchmark/README.md): attack categories, metrics and reproducibility.
- [OWASP mapping](owasp-rag-security.md): primary security reference and backlog mapping.
- [Provenance](provenance.md): source revision and attribution.
- [Historical documentation](base-project/README.md): inherited implementation details, not RagSec guarantees.
- [Commit policy](commit-policy.md): Conventional Commit types, scopes and review rules for maintainable history.

The inherited UI and university dataset remain demonstration fixtures. The protected lab is implemented and verified within the evidence and limitations in the implementation report; historical production, compliance and test-count claims have not been adopted for RagSec.
