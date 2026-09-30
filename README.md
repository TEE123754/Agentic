# FrictionLab

FrictionLab is a local-first synthetic UX audit platform under phased construction. Phases 0–2 established local model feasibility, validated configuration, fixtures, and the trusted browser broker. Phase 3 adds one autonomous persona through bounded smolagents tools. Autonomous cohorts remain disabled. See [implementation plan](IMPLEMENTATION_PLAN.md) and [verified progress](docs/phase-status.md).

## Phase 3 autonomous persona

```powershell
& '.venv\Scripts\python.exe' -m frictionlab autonomous --persona impatient_mobile --journey checkout_review
```

A local model chooses actions against a fresh disposable fixture, independently verifies the goal, and saves detailed offline reports for success, failure, or preflight rejection. All three supported profiles have verified typed-tool journeys after repairs; 100 distinct checks pass. The generated-code/container worker is built in source and awaits its real-host gate. The manual [remote isolation workflow](docs/phase3-remote-gate.md) uses a disposable GitHub runner, leaving this laptop unchanged. No production URL or paid key is accepted. See the [autonomous runner guide](docs/phase3-autonomous.md) and [acceptance record](docs/phase3-validation.md).

## Phase 4 behavioral run

```powershell
& '.venv\Scripts\python.exe' -m frictionlab behavioral --persona impatient_mobile --journey checkout_review --variant dead_button
```

This opt-in mode records grounded interface friction and a versioned patience ledger. A synthetic user stops at zero patience with a terminal evidence snapshot and first-person, evidence-linked diagnosis. The owned-fixture Phase 4 gate passed 109 distinct checks using a deterministic semantic-control acceptance harness, and one repaired run with the actual local Qwen planner reached the defective button and abandoned with evidence. It uses only the disposable fixture and never changes a deployed website. See the [cognitive runtime guide](docs/phase4-cognition.md) and [acceptance record](docs/phase4-validation.md). Full audit recommendations, cohorts, and dashboard remain later phases.

## Phase 2 browser demo

```powershell
& '.venv\Scripts\python.exe' -m frictionlab browser-demo
```

This starts a disposable local storefront, controls a fresh browser through typed actions, checks protection against an independent local sentinel, and saves detailed offline evidence/reports. It requires no model, paid provider, or production URL. See [browser guide](docs/phase2-browser.md) for variants, profiles, and protection limits.

## Start Phase 1

```powershell
& '.venv\Scripts\python.exe' -m frictionlab serve
```

Open `http://127.0.0.1:8765/`. Choose the healthy storefront or one of five deliberate UX defects. All accounts and integration events are synthetic and local. **Reset this run** clears only the current namespace.

```powershell
& '.venv\Scripts\python.exe' -m frictionlab validate configs\run.example.json
```

Configuration review runs offline. Cohort API run requests remain blocked with a factual partial report until orchestration is implemented; single-persona autonomy uses the CLI above. The Phase 2 demo supports only owned fixtures. No production URL is accepted. [Phase 1 guide](docs/phase1-foundation.md) covers the foundation API, reset, contracts, and reports.

## Setup on this Windows machine

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) '.cache\uv'
uv sync --locked --python 'C:\Users\Edison Tee\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& '.venv\Scripts\python.exe' scripts\setup_resources.py --download
```

The first command installs locked free dependencies. The resource command downloads the official llama.cpp runtime and approximately 2.5 GB of quantized Qwen weights for Phase 0 and later agent work; it is not required to serve Phase 1. Assets stay in this project. No paid key is required.

## Phase-boundary validation

Run acceptance checks once after completing each phase; rerun only affected checks after a failure. Phase 1 commands and recorded results are in its guide. The earlier Phase 0 acceptance command is:

```powershell
& '.venv\Scripts\python.exe' spikes\phase0\run.py
```

It starts a local fixture, deny-by-default proxy, disallowed-service sentinel, local planner, and fresh headless Chrome profile. It captures browser-use candidates from the exact Playwright page, executes a model-selected action through Playwright, checks the outcome, measures memory/latency, shuts down, and writes a detailed report under `artifacts/phase0/`.

No real website URL is accepted. Do not use this spike to test production. The isolated container boundary for generated-code agents remains a later prerequisite.

Optional screenshot inspection is configured but disabled. Enabling it requires separately downloaded, pinned local SmolVLM weights and the optional `vision` dependencies; do not enable it implicitly during a run.
