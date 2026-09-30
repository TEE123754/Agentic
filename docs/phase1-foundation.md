# Phase 1 foundation

The application now has an importable `frictionlab` package, shared Pydantic contracts, offline configuration resolution, a FastAPI fixture, and static partial report export. No API key, browser, model, container, external database, or cloud service is needed to start Phase 1.

## Tech stack and files

| Component | Technology | Location |
|---|---|---|
| Local application/API | Python 3.12, FastAPI, Uvicorn | `frictionlab/api.py`, `frictionlab/__main__.py` |
| Validation and report contracts | Pydantic v2, JSON Schema | `frictionlab/contracts/`, `docs/schemas/` |
| Configuration registry | Local JSON, SHA-256 reproducibility hash | `configs/`, `frictionlab/configuration.py` |
| Test storefront | HTML, CSS, JavaScript; relative fetch calls | `frictionlab/fixtures/web/` |
| Synthetic accounts and integrations | In-memory Python store, UUID namespaces | `frictionlab/fixtures/store.py` |
| Report export | Standard-library JSON/Markdown/escaped HTML | `frictionlab/reporting.py` |
| Phase acceptance | pytest, HTTPX/FastAPI TestClient, Ruff, Node syntax check | `tests/phase_01/` |
| Dependency lock | uv; GitHub/open-source packages already recorded | `pyproject.toml`, `uv.lock`, `docs/dependency-manifest.json` |

Playwright, browser-use, and the Phase 0 local Qwen/llama.cpp resources are retained for subsequent phases. Phase 1 does not execute them. DuckDB, Phoenix, smolagents, vision models, Mind2Web, and the Streamlit dashboard remain later work; they are not represented as completed here.

## Start and review configuration

From the project root:

```powershell
& '.venv\Scripts\python.exe' -m frictionlab serve
```

Open `http://127.0.0.1:8765/`. Select a fixture variant and choose **Open variant**. API documentation is at `/docs`; health is `/health`. The command always binds to numeric loopback. A custom unprivileged `--port` requires the environment manifest's origin to match before configuration can pass. It does not enable arbitrary targets.

Review the example configuration without opening a browser:

```powershell
& '.venv\Scripts\python.exe' -m frictionlab validate configs\run.example.json
```

The example resolves three profiles × three journeys × one repetition = nine requested sessions. Its hash includes the resolved profiles, journeys, policy, repetition count, and seed; the generated run ID is excluded so equivalent configurations have the same hash. Profiles describe capabilities and tolerances, not measured human demographics.

`POST /configuration/review` accepts the same JSON and returns validation results. `POST /runs` always returns HTTP 409 with a partial report in Phase 1, including for invalid/non-object/malformed configurations. Accepted configuration is separate from permission to execute a browser. A duplicate explicit run ID cannot overwrite a report.

## Controlled variants

| Variant | Deliberate behavior |
|---|---|
| `healthy` | Checkout feedback, explicit shipping cost, helpful field validation, dismissible policy dialog |
| `generic_validation` | Invalid initial email and an uninformative “Invalid input” message |
| `dead_button` | Start checkout produces no transition |
| `delayed_feedback` | 2.5-second wait before validation without progress feedback or button lock |
| `hidden_shipping` | Product view omits shipping/total; order review exposes the $5 shipping charge |
| `focus_trap` | Delivery dialog disables dismissal and blocks Tab/Escape |

Variants are mutually exclusive in this initial fixture. The API returns an explicit defect manifest for each namespace. Rendering, focus behavior, latency measurement, and automated browser journey verification are Phase 2 acceptance work; Phase 1 validates the state/API contracts and JavaScript syntax.

## Synthetic data and reset

The page creates a fresh UUID namespace and one synthetic account. Accounts use deterministic UUIDs and `@fixture.invalid` addresses, with the full run UUID in the email. Synthetic details produce an order review only; no order is created.

For API usage:

1. `POST /fixture/runs` with `{"run_id":"<UUID>","variant":"healthy"}`.
2. `POST /fixture/runs/<UUID>/accounts` to get the next synthetic account.
3. `POST /fixture/runs/<UUID>/checkout` with `{"email":"<synthetic address>"}`.
4. `POST /fixture/runs/<UUID>/reset` to clear that namespace's accounts, attempts, and mock events. Its variant stays fixed and the account sequence restarts deterministically. Other namespaces remain intact.

**Reset this run** in the page performs the reset and creates its initial account again. API reset itself leaves zero accounts. A new namespace is needed to change variants. Data is deliberately in memory and disappears when the service stops; durable run/evidence storage arrives in Phase 5. Bounded execution and cleanup arrive in Phase 2.

Payment, email, SMS, webhook, inventory, and analytics endpoints only append local mock events. `/fixture/runs/<UUID>/order` is forbidden. `/fixture/sentinel/attempt` records a rejected mock dispatch with zero delivered requests. This sentinel route is a control fixture, not a transport firewall; Phase 0's independent sentinel remains available for Phase 2 network testing.

## Protection and reports

Configuration permits one bundled numeric-loopback origin, synthetic credentials, all six mocks, a disposable data declaration, blocked service workers, four prohibited operations, and bounded traffic settings. External origins, dependencies, literal credentials, incomplete isolation, and a mismatched server origin fail offline. Manifest declarations are not network proof. Browser protection, rate enforcement, process isolation, redirects/beacons/WebSockets, and generated-code isolation are not implemented in Phase 1. Browser run requests are blocked for that reason.

Every blocked run writes eleven report sections in JSON, Markdown, and self-contained HTML under `artifacts/phase1/runs/<run UUID>/`. CLI validation failures use `artifacts/phase1/configuration/<run UUID>/`. Download links read saved files only. HTML contains no remote scripts or connections and escapes report content. Reports explicitly show zero executed sessions, missing browser evidence, and an unvalidated network boundary. No UX defect, abandonment explanation, or heatmap is fabricated. A pre-navigation failure/cancellation/interruption can use the same deterministic partial-report helper.

Report contracts separate execution status from report status, require evidence for findings/friction, validate denominators and candidate identity, reject escaping evidence paths, and require a complete evidence review and disposition for every finding before `ready`. The full evidence review/finalization/recovery pipeline remains Phase 7.

## Validation policy

Build the phase completely, then run one phase acceptance pass:

```powershell
& '.venv\Scripts\python.exe' -m pytest tests\phase_01 --junitxml=artifacts\phase1\validation.xml
& '.venv\Scripts\ruff.exe' check frictionlab tests\phase_01 scripts\export_schemas.py
node --check frictionlab\fixtures\web\app.js
```

Only rerun affected checks to repair a failure. The suite denies outbound socket connections and DNS lookups, uses the API in-process, and never launches a browser, model, cohort, or Phase 0 scenario. See `phase1-validation.md` for the recorded result.

To regenerate contract schemas after an intentional contract change:

```powershell
& '.venv\Scripts\python.exe' -m scripts.export_schemas
```
