# RagSec testing

## Available today

The inherited test suite remains in `backend/tests/`. Install the pinned security requirements in an isolated Python 3.12 environment, then run from the repository root:

```bash
python -m pytest backend/tests/ -q
```

The protected offline lane requires a real local OPA process because authorization tests must exercise the Rego policy, not an allow-only mock:

```bash
docker run --rm -d --name ragsec-test-opa -p 127.0.0.1:18181:8181 \
  -v "$PWD/policies:/policies:ro" openpolicyagent/opa:1.4.2-static \
  run --server --addr=0.0.0.0:8181 /policies
RAGSEC_TEST_OPA_URL=http://127.0.0.1:18181 .venv/bin/python -m pytest tests/ -q
```

Run the complete local check with `RAGSEC_TEST_POSTGRES_URL` and `RAGSEC_TEST_QDRANT_URL` set to the disposable integration services. `tests/test_services.py` verifies the migration chain and that the Qdrant query key cannot write. Run `opa check --strict policies/` and `opa test policies/ -v` for policy evidence. The frontend build is `npm --prefix frontend run build`; browser coverage is `npm --prefix frontend exec playwright test` after the protected API and frontend are running.

The CI workflow continues to test the backend and build the frontend and Docker images. These checks are baseline regression coverage, not evidence of firewall effectiveness.

## Planned security validation

Use `tests/` for deterministic scanner and policy tests, integration tests of every enforcement boundary, and parity checks for REST/SSE. Test missing metadata, policy outages, revocation, cache reuse, malicious tool results, memory ownership and cross-chunk output leaks. A denied action must have zero executed side effects.

The CI workflow runs these OPA checks and the offline firewall lane. The protected Compose profile is local-lab deployment evidence; TLS termination and external provider retention remain deployment decisions.

Use [benchmark protocol](../benchmark/README.md) for live-model experiments. Keep model-dependent evaluations separate from offline unit tests. No published test count or performance claim should be copied from historical documents without a current run.
