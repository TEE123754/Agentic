# FrictionLab

**Find interface friction before release, with synthetic users and evidence you can review.**

FrictionLab is an open-source Python tool for product and engineering teams investigating difficult user journeys. Configurable personas navigate disposable web fixtures, record interaction friction, and produce detailed audits with screenshots, patience changes, abandonment explanations and remediation advice.

[Product landing page](site/index.html) | [Sample offline audit](examples/phase9-static/index.html) | [Implementation plan](IMPLEMENTATION_PLAN.md) | [Verified progress](docs/phase-status.md)

## What teams can inspect

- Behavioral evidence: failed interactions, validation, stalled progress and evidence-linked synthetic abandonment diagnoses.
- Cohort results: completion, abandonment, blocked and infrastructure-failure counts, with inconclusive sessions visible.
- Actionable audits: prioritized findings, observations, inferred mechanisms, recommendations and verification steps.
- Replay and review: saved screenshots, compatible synthetic click heatmaps, finding dispositions and report revisions.
- Comparisons: matched fixture baseline/candidate results with raw counts and exclusions.
- Portable reports: JSON, Markdown and HTML, plus an interactive viewer that works without the backend.

## Current scope

This is a development-stage tool. Phases 0-9 passed their declared owned-fixture and offline-sharing gates. See the [Phase 9 validation record](docs/phase9-validation.md). Synthetic persona behavior is not a prediction of human conversion or proof of human usability.

**Execution currently accepts bundled disposable fixtures only.** Arbitrary deployed products and external staging replicas remain blocked. Future replica support requires separate data, mocked integrations and a proven network boundary. FrictionLab provides advice; it does not change application source or deploy fixes. Reports and replay read saved evidence without contacting the tested website.

The current planner uses local llama.cpp/Qwen. **Phase 10 adds an installable `frictionlab` CLI and opt-in Groq/Gemini inference using your own API key.** See the [local installation and BYOK guide](docs/phase10-installation.md). Cloud transports are built; their phase gate and live-account verification status are recorded in the implementation plan. The application, browser and evidence remain local. BYOK inference sends bounded sanitized semantic inputs to the chosen provider; fully offline inference uses a local model without a key. No FrictionLab account, subscription or billing proxy is required. Provider free-tier availability is not guaranteed.

## Download and run from source

Install Git, Python 3.12 and [uv](https://github.com/astral-sh/uv). Clone this repository or download its ZIP from GitHub's **Code** menu, then open a terminal in the extracted directory.

```sh
git clone https://github.com/TEE123754/Agentic.git
cd Agentic
uv sync --locked --extra dashboard
uv run frictionlab --help
uv run frictionlab init ../frictionlab-workspace
uv run frictionlab doctor
```

GitHub access depends on repository visibility; public publication is a later release step. Development wheel/source downloads are produced by the Phase 10 GitHub Actions workflow; install instructions and free-account configuration are in the [operator guide](docs/phase10-installation.md). No package-index publication is promised here.

For the local fixture/API and dashboard, use two terminals:

```sh
uv run frictionlab serve
uv run frictionlab dashboard
```

Open `http://127.0.0.1:8501` for the dashboard. Automation requires a compatible local Chromium/Chrome path; follow the [browser setup guide](docs/phase2-browser.md). Autonomous runs need either an opted-in BYOK provider or the separately configured local model resources in the [autonomous runner guide](docs/phase3-autonomous.md). Model downloads are optional setup steps and can be several GB; opening a saved report needs none.

```sh
uv run frictionlab behavioral --persona impatient_mobile --journey checkout_review --variant dead_button
```

Profiles include an impatient mobile shopper, a keyboard/low-vision user and an enterprise evaluator. These are explicit synthetic configurations, not clinical or demographic simulations.

Use `frictionlab cohort --variant dead_button` for a detailed cohort audit. It defaults to one profile, one journey and one worker. `doctor` checks local setup without any browser/model launch or network request. Configure your workspace and key as described in the operator guide before running.

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
| Review | Streamlit, Plotly, bundled HTML/CSS/JavaScript | Dashboard, comparisons and offline viewer |
| Evaluation | [Mind2Web](https://huggingface.co/datasets/osunlp/Mind2Web), owned fixtures | Reference scoring and controlled acceptance |
| Delivery | GitHub, uv; optional static hosting | Source downloads and reproducible phase gates |

Mind2Web reference scores are separate from actual planner evaluation. Optional vision and Phoenix integration should be checked against the implementation plan; neither is required for report review. Dependencies, models and datasets retain their own licenses.

## Development and roadmap

[Phase 10](docs/phase10-local-product.md) records local CLI distribution and BYOK implementation/verification. Phase 11 covers clean installation, consolidated regression and pilot release validation. External replicas and human calibration remain additional work.

Acceptance runs once after construction; rerun affected failures only. See [CONTRIBUTING](CONTRIBUTING.md), [SECURITY](SECURITY.md) and the [implementation plan](IMPLEMENTATION_PLAN.md). Project code is licensed under [MIT](LICENSE); third-party components retain their notices.
