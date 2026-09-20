# Commit policy

RagSec uses [Conventional Commits](https://www.conventionalcommits.org/) so the history communicates intent and can be released or audited predictably.

Use this format:

```text
<type>(<scope>): <imperative summary>
```

Preferred types are `feat` for new behavior, `fix` for defect or security remediation, `test` for coverage and fixtures, `docs` for documentation, `refactor` for behavior-preserving restructuring, `build` for dependencies or packaging, and `ci` for automation. Keep the summary imperative, specific and under roughly 72 characters. Use a body when the security rationale, compatibility impact or validation command is not obvious. Add `BREAKING CHANGE:` only when an interface or operational contract requires migration.

Security changes should be split by reviewable boundary where practical: enforcement/runtime, policy, tests/benchmark, deployment/dependencies and documentation. Each commit must build on its own, avoid credentials or private traces, and mention the relevant test command in its body or pull request. Do not combine historical-document edits with changes that alter current security claims.
