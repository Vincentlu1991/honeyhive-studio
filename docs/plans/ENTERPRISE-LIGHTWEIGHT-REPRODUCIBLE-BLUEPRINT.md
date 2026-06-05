# Enterprise Lightweight Reproducible Blueprint

## North Star
Build a production-grade, local-first, multi-agent application that is:
- Enterprise-grade: secure, observable, governable.
- Lightweight: minimal runtime footprint and simple operations.
- Reproducible: deterministic runs and one-command setup.

## Delivery Phases

### Phase P0 - Security and Portability (Week 1)
Goals:
- Remove secret leakage risk.
- Eliminate machine-specific hardcoded paths.
- Disable heavy debug behavior by default.

Acceptance criteria:
- No real credentials in tracked files.
- All startup paths come from configuration.
- Debug workflow dumps are off by default.

### Phase P1 - Reliability and Quality Gate (Week 1-2)
Goals:
- Standardize health checks and failure handling.
- Harden QA logic and remove duplicated implementations.
- Build a deterministic quality gate for local and CI use.

Acceptance criteria:
- One command runs compile, lint, tests, and integration checks.
- Retry and fallback behavior is covered by tests.
- Runtime failures produce actionable diagnostics.

### Phase P2 - Performance and Reproducibility (Week 2+)
Goals:
- Reduce latency and memory pressure in hot paths.
- Introduce benchmarkable KPIs.
- Make outputs reproducible with immutable run metadata.

Acceptance criteria:
- Throughput and latency metrics are recorded per run.
- Seed/workflow/model parameters are persisted for replay.
- Data-heavy views use pagination and lazy loading.

## Mandatory Operating Rules

### Security
- Keep secrets only in local env files that are git-ignored.
- Rotate compromised tokens immediately.
- Add pre-commit checks for secret patterns.

### Observability
- Track run success rate, avg latency, retry rate, fallback rate.
- Log major stage transitions: planning, prompting, render, QA.
- Keep debug artifacts optional and disabled by default.

### Reproducibility
- Pin package versions in requirements.
- Persist each run with seed, workflow path, model, and retry trace.
- Provide replay command examples in README.

## KPI Dashboard (Minimum)
- Success rate >= 90%
- Median end-to-end latency trend
- Retry ratio < 25% for stable workflows
- Fallback usage trend (LTX -> SD15)
- QA pass rate trend

## Execution Backlog (Current)
1. Security hardening: token sanitation and env governance.
2. Remove hardcoded local paths from app/runtime code.
3. Turn off default workflow debug dump.
4. Deduplicate QA implementation and add coverage.
5. Add unified enterprise quality gate command for CI.

## Definition of Done
A release is done only if:
- Security checks pass.
- Quality gate passes end-to-end.
- Reproducibility metadata is stored and replayable.
- Core KPIs are visible and stable for at least one week.
