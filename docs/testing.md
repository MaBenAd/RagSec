# RagSec testing

## Available today

The inherited test suite remains in `backend/tests/`. Install the base requirements in an isolated environment, then run from the repository root:

```bash
python -m pytest backend/tests/ -q
```

The CI workflow continues to test the backend and build the frontend and Docker images. These checks are baseline regression coverage, not evidence of firewall effectiveness.

## Planned security validation

Use `tests/` for deterministic scanner and policy tests, integration tests of every enforcement boundary, and parity checks for REST/SSE. Test missing metadata, policy outages, revocation, cache reuse, malicious tool results, memory ownership and cross-chunk output leaks. A denied action must have zero executed side effects.

Add `opa test policies/ -v` and `opa check --strict policies/` to CI when OPA is installed and policies gain tests. Current Rego files are deny-all scaffolds with no allow rules or runtime integration.

Use [benchmark protocol](../benchmark/README.md) for live-model experiments. Keep model-dependent evaluations separate from offline unit tests. No published test count or performance claim should be copied from historical documents without a current run.
