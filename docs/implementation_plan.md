# HongCe Implementation Plan

## Phase 0 Audit

Workspace status:

- Project root: `/Users/dzkdemacbook/Documents/Codex/2026-08-05/ai-ai-50-what-if-api`
- Initial source tree: empty except `work/` and `outputs/`
- Git status: not a Git repository
- Source materials:
  - `/Users/dzkdemacbook/Downloads/CODEX_IMPLEMENTATION_BRIEF_HongCe.md`
  - `/Users/dzkdemacbook/Downloads/HongCe_full_social_simulation_proposal.docx`
  - Extracted DOCX audit copy: `work/HongCe_full_social_simulation_proposal.extract.md`

Runtime audit:

- Node.js: bundled runtime available
- pnpm: bundled runtime available
- Python: bundled runtime available
- Present Python packages: `pydantic`, `numpy`, `pandas`
- Missing packages in current environment: `pytest`, `networkx`, `fastapi`

## Frozen MVP Scope

HongCe is a policy stress-testing system, not a flood forecasting, engineering assessment, or automatic command system.

MVP must implement:

- Synthetic Qingyuan county.
- Six actor classes: residents/families, institutions, community workers, governments, professional departments, rescue forces.
- At least four network layers: family/care, neighbor, institution, administrative. Target six layers adds volunteer and online networks.
- 5-minute crisis timestep.
- Explicit last-mile state chain and failure states.
- S0, S3, S5 first, then S1/S2/S4.
- Results from actual simulation runs only.
- No external model key requirement.

## Frozen Data Labels

- `FACT`: traceable public facts, used only to calibrate structure and scale.
- `SYNTHETIC`: generated county, population, institutions, networks, facilities, parameters.
- `SIMULATED`: actual outputs from the current code version and seed set.

## Frozen Data Objects

Implemented as Phase 0 contracts in `src/hongce/models.py`:

- `PersonAgent`
- `Household`
- `Institution`
- `NetworkEdge`
- `InfrastructureNode`
- `WarningEvent`
- `MessageReceipt`
- `EvacuationTask`
- `ResourceUnit`
- `DecisionTrace`
- `SimulationRun`
- `PolicyConfig`
- `MetricRecord`

## Frozen State Machine

Primary chain:

```text
uncontacted -> contacted -> confirmed -> waiting_transfer -> in_transit -> sheltered
```

Explicit delay/failure states:

- `unregistered`
- `contact_failed`
- `misunderstood`
- `distrusted`
- `refused`
- `resource_blocked`
- `route_blocked`
- `authorization_wait`
- `unsuitable_shelter`

The system must never treat message receipt, understanding, trust, confirmation, resource assignment, and sheltering as the same state.

## Frozen MVP Policies

- S0: static roster, department one-way push, no confirmation requirement, equal allocation, routine inspection.
- S3: dynamic roster, department push plus cadre call, confirmation required, vulnerable-first dispatch, care resources prepositioned.
- S5: dynamic roster, multi-channel/cadre/neighbor/backup communication, confirmation required, resilience dispatch, bridge/communication/routine maintenance.

## Frozen Metrics

Minimum metric records:

- Safe-before-danger rate.
- Vulnerable harm risk.
- Median effective lead time.
- Response closure rate.
- Missed critical action rate.
- Group safety gap.
- Incremental cost per safe transfer.
- Worst-case regret.
- Trust delta.
- Resource queue time.

## Implementation Sequence

### Phase 1: Reproducible Simulation Kernel

- Generate Qingyuan synthetic county, people, institutions, facilities, routes, and multilayer networks.
- Implement deterministic hazard timeline and facility state updates.
- Implement message propagation, receipt, understanding, trust, confirmation, and task conversion.
- Implement resident evacuation probability with decomposed factors.
- Implement constrained resource dispatch and route blocking.
- Implement S0/S3/S5 and CLI end-to-end run.
- Add core tests for state transitions, resources, roads, reproducibility, metrics, and edge cases.

### Phase 2: Batch Experiments and Explanation

- Monte Carlo runner for S0/S3/S5 with shared population/network/hazard and policy-only changes.
- Run summaries with means, medians, quantile intervals, and worst cases.
- Implement Experiments A/B/C.
- Add individual, organization, facility, and policy explanation outputs.
- Generate validation report and result artifacts.

### Phase 3: API and Frontend

- Add FastAPI endpoints from the brief.
- Build React/Vite frontend with seven required pages.
- Ensure UI reads only API outputs or versioned actual run artifacts.
- Add loading/error/cancel states and smoke tests.

### Phase 4: Remaining Policies and Adapters

- Implement S1/S2/S4.
- Add `YulanOneSimAdapter` protocol if official API is verifiable.
- Keep `RuleBasedAgentAdapter` as the default no-key execution path.
- Add model-off, cache, and replay controls.

### Phase 5: Competition Delivery

- Complete technical document, model card, data card, validation report, parameter dictionary.
- Write demo script and recording checklist.
- Regenerate locked S0/S3/S5 results with fixed seeds.
- Re-run clean install, tests, simulations, build, and demo reset commands.

## Phase Reporting Template

Each phase report will include:

- Implemented runnable capability.
- Key files.
- Verification commands and results.
- Current limitations.
- Next phase.
