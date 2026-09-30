# Phase 7 local command center

The Streamlit dashboard is a local UI for the owned storefront fixture. It reads saved runs, reports, screenshots, and heatmaps through the FastAPI service. It never opens the tested page while reviewing results and does not connect directly to DuckDB. Streamlit and Plotly are free, open-source optional dependencies; no cloud account or paid API is required.

## Start

From the repository root, install the optional dashboard once with `uv sync --locked --extra dashboard --group dev`. In one terminal run `uv run python -m frictionlab serve`. In another run `uv run --extra dashboard python -m frictionlab dashboard`, then open `http://127.0.0.1:8501`. Both services bind only to `127.0.0.1`. The dashboard expects the API at `http://127.0.0.1:8765` by default; `FRICTIONLAB_API_BASE` may name another explicit `127.0.0.1` HTTP port.

New cohorts still require the prior-phase local model runtime. To inspect saved results, only the API and dashboard need to run. The setup form exposes registered profiles, journeys, seed, repetitions, and fixture variants; it displays the fixed network, runtime, and six-session ceilings. It does not accept an external URL or live credentials. Launching a run uses the existing configuration validator and fixture-only browser boundary.

## Review

The execution panel refreshes saved status every three seconds and shows last action, step count, elapsed time, patience, and cancellation controls. It does not infer a browser action before one is saved. The Overview separates executed/eligible counts and shows outcome and milestone charts plus protection, exclusions, and missing-evidence reasons. Trajectories display stored masked screenshots, focus, validation, action results, and patience changes. Heatmaps filter by compatible route, input mode, CSS viewport, and capture pixel dimensions. Findings show observed behavior separately from a possible mechanism, severity, eligible denominator, affected profiles, direct masked evidence, remediation, and verification. A human disposition creates a later immutable report revision. The full report can be read and downloaded as JSON, Markdown, or HTML.

Evidence endpoints serve only assets referenced by a run's saved session or report. The dashboard API client accepts only an explicit loopback URL and rejects redirects. Screenshots and SVGs are rendered from local API bytes, never from the tested website. The API remains limited to the bundled fixture; external staging use needs a separate validated no-impact replica boundary.

The manual `.github/workflows/phase7-dashboard.yml` workflow runs the end-of-phase acceptance on an ephemeral GitHub runner, keeping browser and Streamlit work off the laptop. It retains synthetic evidence for seven days and writes an offline validation review. Fix a failure with an affected-only rerun rather than repeating passing phase suites.
