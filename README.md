# FrictionLab

**Find interface friction before release, with synthetic users and evidence you can review.**

FrictionLab is an open-source Python tool for product and engineering teams investigating difficult user journeys. It combines a simple local website assessment dashboard with controlled synthetic-user cohorts. Teams can inspect offline snapshots, review evidence-backed findings, and investigate behavioral friction on disposable fixtures.

[Product landing page](https://tee123754.github.io/Agentic/) | [Sample offline audit](examples/phase9-static/index.html) | [Implementation plan](IMPLEMENTATION_PLAN.md) | [Verified progress](docs/phase-status.md)

## Download

- [Windows desktop ZIP and SHA256SUMS](https://github.com/TEE123754/Agentic/releases/tag/v0.1.0): extract the ZIP and open `FrictionLab.exe`. Chrome or Edge is needed for viewport and accessibility inspection. Connect your own eligible AI key in the native launcher when you want AI advice.
- [Source, Python wheel and checksums](https://github.com/TEE123754/Agentic/releases/tag/v0.1.0): use Python 3.12 and uv for the CLI. No bundled model or browser download is required for URL-only checks.
- [Public product landing](https://tee123754.github.io/Agentic/) and [detailed setup and safety scope](docs/local-assessment.md).

These releases are development builds for the declared offline and owned-fixture gates. A score must be read alongside coverage, skipped checks and the report's limitations.

## Start a local assessment

```sh
git clone https://github.com/TEE123754/Agentic.git
cd Agentic
uv sync --locked
uv run frictionlab start
```

The CLI opens a localhost dashboard. Paste a URL, choose an evidence source, select individual checks or all six categories, and start. Connect your own Groq or Gemini key in the dashboard if you want AI recommendations. Core structural checks work without a key. No models or browsers download automatically.

For the native desktop launcher:

```sh
uv run frictionlab desktop
```

The native window provides masked key setup and start/open/stop controls for the same local assessment workspace. Optional remembering uses your OS credential store; session-only keys never become plaintext files. The [Windows portable ZIP](https://github.com/TEE123754/Agentic/releases/download/v0.1.0/FrictionLab-windows-x64.zip) contains the desktop app. Read the [setup, safety and category coverage guide](docs/local-assessment.md) before running it.

## What you receive

- Overall and per-category scores accompanied by executed coverage and confidence.
- Severity-ranked issues with observations, reproduction steps and practical recommendations.
- Passed, failed, skipped and incomplete checks, with missing prerequisites visible.
- Progress, cancellation, local history, three viewport screenshots and JSON/Markdown/HTML/ZIP exports.
- Optional bounded AI advice for measured findings; provider faults retain the deterministic report.
- Existing owned-fixture cohort tools for synthetic behavioral journeys, patience, abandonment evidence, replay and comparisons.

## Production protection and current scope

**Browser isolation alone cannot prevent production side effects.** URL-only inspection makes no DNS or website requests. Uploaded offline snapshots are rendered on a synthetic origin with application scripts, forms, frames, workers and external requests disabled. This dashboard never navigates its inspection browser to your submitted URL.

Public HTML capture is a separate, explicitly approved one-GET operation, without authentication, redirects or subresource fetching. A GET can affect logs or trigger server state changes: use an uploaded snapshot when zero target contact is required.

| Category | Available offline evidence | Additional access required |
|---|---|---|
| Functionality | Declared link structure | Interactive flows, APIs and integrations require an isolated application/backend. |
| Usability | Titles, headings and structural signals | Cognitive journeys require an isolated interactive replica; real churn needs human calibration. |
| Accessibility | Alt/label declarations and axe-core | Keyboard, screen reader and compliance conclusions require interactive/manual review. |
| Responsiveness | Viewport metadata and three static viewport checks | Dynamic layouts and complete asset fidelity require a replica. |
| Performance | HTML size heuristic | Real load measurements and Core Web Vitals require a controlled replica/benchmark. |
| Security | URL scheme; selected original headers on approved capture | TLS/server configuration, source/dependency and auth/exploit checks require additional access and authorization. |

Unsupported work is explicitly skipped. An unavailable browser or interrupted check is incomplete. Scores do not count unknown checks as passing and are not production readiness or security certification.

Autonomous browser execution still accepts **bundled disposable fixtures only**; arbitrary deployed/staging application workflows remain blocked until a separate backend/data/integration boundary is verified. FrictionLab provides advice and does not modify application source or deploy fixes. Local report review does not contact the tested website. Screenshot pixels can contain supplied content: review exports before sharing.

## Existing behavioral cohort workflow

For deeper controlled persona investigations, see the [local CLI/BYOK guide](docs/phase10-installation.md) and [autonomous runner guide](docs/phase3-autonomous.md). Local model downloads are optional and can be several GB; the new snapshot dashboard does not need them. Cloud inference sends opted-in sanitized inputs to your chosen provider and uses your own eligible account. Free-tier availability and quotas are not guaranteed; no paid fallback is provided.

```sh
uv run frictionlab doctor
uv run frictionlab cohort --variant dead_button
```

Synthetic personas include an impatient mobile shopper, a keyboard/low-vision user and an enterprise evaluator. They are explicit behavioral configurations, not demographic, clinical or human conversion predictions. The older Streamlit cohort review uses `frictionlab serve` and `frictionlab dashboard`; the simple assessment interface uses the single `frictionlab start` command.

## Inspect and share a report

Open `examples/phase9-static/index.html` directly in your browser to explore a synthetic audit without installing Python. Open `site/index.html` for product information and documentation links.

```sh
uv run frictionlab export-static RUN_UUID --root artifacts/phase5 --output artifacts/my-audit
```

Replace `RUN_UUID` with a saved cohort run identifier and use a new output directory. Export creates an offline viewer and importable JSON; no upload occurs. Review screenshots and prose before sharing. Read the [sharing guide](docs/phase9-sharing.md) for limits and optional static hosting.

## Technology

| Layer | Open-source tools | Role |
|---|---|---|
| Browser | [Playwright Python](https://github.com/microsoft/playwright-python), [browser-use](https://github.com/browser-use/browser-use) | Controlled Chromium actions and semantic grounding |
| Planning | [smolagents](https://github.com/huggingface/smolagents), [llama.cpp](https://github.com/ggml-org/llama.cpp), local Qwen | Bounded agent tools and local inference |
| Runtime/API | Python, Pydantic, FastAPI, uvicorn | Persona budgets, cohorts and local APIs |
| Storage/traces | DuckDB, OpenTelemetry | Local structured evidence and execution records |
| Review | FastAPI/local HTML/CSS/JavaScript; Streamlit/Plotly for cohorts | Assessment dashboard, comparisons and offline exports |
| Desktop/keys | Tkinter/ttk, keyring, PyInstaller | Native launcher, OS credential storage and Windows packaging |
| Evaluation | [Mind2Web](https://huggingface.co/datasets/osunlp/Mind2Web), owned fixtures | Reference scoring and controlled acceptance |
| Delivery | GitHub, uv; optional static hosting | Source downloads and reproducible phase gates |

Mind2Web reference scores are separate from actual planner evaluation. Optional vision and Phoenix integration should be checked against the implementation plan; neither is required for report review. Dependencies, models and datasets retain their own licenses.

## Development and roadmap

[Phase 10](docs/phase10-local-product.md) records local CLI distribution and BYOK implementation/verification. Phase 11 covers clean installation, consolidated regression and pilot release validation. External replicas and human calibration remain additional work.

Acceptance runs once after construction; rerun affected failures only. See [CONTRIBUTING](CONTRIBUTING.md), [SECURITY](SECURITY.md) and the [implementation plan](IMPLEMENTATION_PLAN.md). Project code is licensed under [MIT](LICENSE); third-party components retain their notices.

The owned-fixture release gate passed: 265 distinct regression cases, healthy real checkout 3/3 completed, with a reviewed partial defect baseline that excludes two planner faults. The offline assessment and Windows desktop gates also passed. FrictionLab 0.1.0 is a public development release with explicit offline and owned-fixture limits. See [Phase 11 results and remaining work](docs/phase11-validation.md) and [release operations](docs/phase11-release.md).
