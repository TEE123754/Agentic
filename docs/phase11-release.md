# Local release candidate operations

Release candidate 0.1.0 supports bundled disposable storefront fixtures only. The three profiles, checkout/review, delivery-information and keyboard journeys are controlled pilot equivalents; they are not three independent customer applications. External URL execution remains blocked. Real human churn, optional vision, Phoenix visualization, arbitrary replicas, live BYOK model quality and Windows/macOS clean archive installation are not release claims.

## Install and choose resources

Follow [the installation guide](phase10-installation.md) for source or archive installation, workspace initialization and explicit BYOK opt-in. Python 3.12 is required. `uv sync --locked --extra dashboard` installs the locked dashboard dependencies. Wheel-only dependency resolution is not the same as the source lockfile. Verify downloaded archive hashes against SHA256SUMS before installation.

Default init selects fully local inference with no API key. Model/runtime downloads occur only through the explicit setup command, never during an audit. From the source checkout or extracted source archive:

```sh
python scripts/setup_resources.py --workspace /absolute/path/to/workspace --download
export FRICTIONLAB_HOME=/absolute/path/to/workspace
export FRICTIONLAB_BROWSER_PATH=/usr/bin/google-chrome
frictionlab doctor
frictionlab cohort --variant dead_button
```

Use the Python executable in your virtual environment; source mode may use `uv run python` and `uv run frictionlab`. PowerShell uses `$env:FRICTIONLAB_HOME` and `$env:FRICTIONLAB_BROWSER_PATH`. Set the workspace to the same directory used by resource setup. The Windows runtime is pinned; macOS runtime is not packaged/configured. Doctor checks executable/file presence, dependency versions and writability without probing a provider or starting services. Model checksum verification and managed-service readiness happen at startup. No external inference is selected in local mode. Do not configure a provider key for the offline pilot.

The optional CPU planner is llama.cpp b11247 with Qwen3-4B Q4_K_M, revision and SHA pinned in resource-manifest.json. It downloads about 2.5 GB of weights plus the runtime. Phase 0 measured combined monitored RSS 5.311 GiB on the recorded Windows laptop; this is a measured observation, not a universal minimum. Default one worker, one inference request, 4,096 context tokens, CPU execution and bounded runtime minimize contention. See [hardware observations](local-hardware-profile.md). Vision weights, GPU acceleration, rootless generated-code containers and Phoenix are optional and are not required for typed-tool execution. No model or container is installed on the operator laptop by the development validation workflow.

## Startup, pilots and reports

Use separate terminals for `frictionlab serve` and `frictionlab dashboard`; both bind loopback. Start with the one-profile quickstart before increasing the cohort. For three profiles use a run JSON containing all three profile IDs and only `checkout_review` (one repetition), then `frictionlab cohort --config PATH --variant dead_button`. The full example has nine cross-product sessions, exceeding the six-session cap; choose a smaller subset rather than raising the cap.

Controlled equivalents: healthy storefront, inert checkout control (`dead_button`), and keyboard/validation/layout defect variants. Tests retain isolation sentinel traffic/data evidence. A mocked semantic acceptance harness checks deterministic detector/dashboard behavior separately from real local model pilots. A successful deterministic harness run is not a model-quality result.

Reports live in workspace `artifacts/phase5/reports/RUN_UUID/revisions/`. They include scope, cohort outcomes, findings/evidence, timelines, patience/abandonment, heatmaps, protection, recommendations, review/limitations and comparison. Open the latest JSON/Markdown/HTML locally, review findings in the dashboard and export with `frictionlab export-static RUN_UUID --output NEW_DIRECTORY`. The bundled `examples/phase9-static/index.html` is a synthetic complete example. Actual pilot reports are retained in release artifacts. [Illustrative partial examples](sample-reports/README.md) are generated from the report contract; never interpret them as executed measurements. See [the incomplete release validation record](phase11-validation.md) before using this development candidate.

## Cancellation, retention and recovery

Cancel through the dashboard/API or Ctrl+C in the owning terminal. Terminal runs preserve partial reports; infrastructure errors are excluded from UX abandonment. On restart the coordinator replays the append-only local journal, marks orphaned work interrupted and reconstructs partial reports. Retry creates a fresh child attempt; it does not silently resume browser state. Report-synthesis failure keeps the earlier partial report rather than discarding evidence. Review saved revisions and limitations before drawing conclusions.

No automatic evidence expiry is implemented. Keep artifacts private; screenshots and traces can contain selected page content even after sanitization. Export only the intended sanitized bundle. Stop run/API/dashboard before archiving a workspace. Preserve the entire cohort root (journal, DuckDB, run manifests, reports and evidence together); manually deleting individual run files can break audit references and recovery. For cleanup, remove only your dedicated workspace/virtual environment after copying the reports you need. The tool closes its owned browser/model/services; cleanup never connects to a deployed product. GitHub development evidence expires after 14 days; copy required archives locally.

## Troubleshooting and network boundary

Missing resources: explicit setup into FRICTIONLAB_HOME, then doctor. Missing browser: set an installed Chrome/Chromium path; audits do not download one. Provider quota/model fault: partial infrastructure report; no paid/provider fallback. Invalid configuration: blocked/failed report before navigation. Incomplete synthesis: retain partial report and inspect the recorded report job. A low patience outcome indicates the modeled profile encountered detector events; it is not a measured human churn probability.

External application isolation requires a separately disposable replica, synthetic dataset, test credentials and integration endpoints, deny-by-default egress, redirect/DNS/subresource/websocket/service-worker boundaries, rate limits, reset/cleanup proof and sentinel observations. A staging hostname alone proves none of these. Current code does not accept arbitrary replicas even when an operator asserts those prerequisites. Replica adapter implementation and independent boundary acceptance must precede that feature.

## Release procedure

`.github/workflows/phase11-release.yml` runs a clean locked installation, explicitly downloads checksum-pinned resources on a disposable Linux runner, builds archives, runs the complete regression once (including API/dashboard, offline export, failure/recovery and real three-profile local pilot), and verifies the installed wheel outside the checkout. Fix failures and rerun only the affected selector. Retain JUnit, dependency license metadata, screenshots, reports and archive hashes. No real provider keys are supplied; no public visibility, package-index upload, GitHub Release or hosted page is created. Those are later publication actions after the release evidence is reviewed.
