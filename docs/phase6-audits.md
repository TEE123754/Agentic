# Phase 6: offline cohort audits

Phase 6 turns saved Phase 5 cohort records into an evidence-reviewed UX audit. It supports only the bundled, owned fixture. Report synthesis and human review read local JSON, masked screenshots, the fsynced event journal, and DuckDB projections. They do not start a browser, call a model, or request the tested application.

## Runtime and free tools

- Python 3.12 and Pydantic validate report and evidence contracts.
- DuckDB stores run, session, finding, and report-job projections; the local JSONL journal supports replay and idempotent finding persistence.
- Playwright and browser-use belong to the earlier execution phases. Phase 6 consumes their saved observations and trajectories only.
- Deterministic Python aggregation groups detector evidence and emits SVG/JSON synthetic click heatmaps. No paid model API or account is required.
- FastAPI serves the latest or an explicit immutable report revision. GitHub Actions can run the single acceptance batch on a free ephemeral runner; its retained evidence is synthetic and short-lived.

## After a cohort finishes

The coordinator writes a durable revision-1 partial report first. The offline audit then validates session identity, build, outcome, network-boundary result, sentinel result, trajectory observation IDs, grounded candidates, event/action alignment, and local evidence paths and sizes. A claim that fails validation is excluded and explained. A synthesis or export fault leaves revision 1 downloadable and records a failed report job for recovery.

Revision 2 groups verified issues by build, route, page-state signature, viewport, interaction mode, detector, and control. Each finding states the observed fact, a separate possible mechanism, affected and eligible synthetic sessions, reproduction fraction, confidence basis, severity rationale, masked evidence, a frontend remedy, and a concrete verification step. It never estimates human conversion or revenue impact.

The milestone funnel counts only eligible completed or patience-abandoned sessions. Cancelled, interrupted, blocked, and infrastructure-failed sessions appear in outcomes and exclusions, outside the UX denominator. Incomplete runs and unsupported evidence produce an explicit partial audit.

Click heatmaps use saved candidate bounds and screenshot coordinate maps. They contain saved synthetic actions, not recordings of real visitors. A repeated-failure cluster requires at least three consecutive distinct failed clicks on the same control in a compatible page state. Common intentional repeat controls are excluded. An SVG includes its masked screenshot as a local data URL, so the offline report does not fetch the target application.

## Inspect and review

For a run ID, the local API provides `GET /runs/{run_id}/reports/json`, `/md`, or `/html`. `GET /runs/{run_id}/reports/revisions/{revision}/{format_name}` retrieves a specific immutable version. A reviewer can submit a local disposition with `POST /runs/{run_id}/findings/{finding_id}/review` and JSON such as `{"status":"confirmed","note":"Reproduced in the saved fixture evidence."}`. This creates a later revision from the already saved audit assets. The disposition is a reviewer judgment, separate from the automated evidence check.

Open `report.html` or `report.md` with the adjacent `evidence/` and `heatmaps/` files retained. The structured `report.json` is the source for a future Phase 7 dashboard. Each export includes the run and protection context, trajectory links, milestone funnel, findings, heatmaps, exclusions, recommendations, and review status.

## Acceptance and limits

The manual workflow `.github/workflows/phase6-audits.yml` runs the Phase 6 suite and relevant regressions once after construction, then reviews the saved files with `scripts/review_phase6.py`. Evidence must show zero target requests during report synthesis/review and no live-sentinel traffic during execution. These assertions cover the owned fixture only. The reports are synthetic diagnoses, not a calibrated prediction of human abandonment; external staging sites, source-file localization, and production traffic are out of scope.
