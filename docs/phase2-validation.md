# Phase 2 acceptance and evidence review

**Date:** September 29, 2026. **Result:** Complete for the owned-fixture browser/proxy gate. **83 distinct checks passed; no unresolved checks.** External replica execution, generated code, and autonomous cohorts remain unavailable.

## Delivered

The trusted broker controls a fresh installed-Chromium profile through Playwright 1.63.0. browser-use 0.13.10 and cdp-use 1.4.5 supply read-only grounding on that same browser target. Python/FastAPI/Uvicorn serve a run-owned copy of the storefront; a fixed-upstream Python gateway enforces endpoint/payload rules and traffic limits. Local axe-core 4.13.0 supplies accessibility signals without a hosted scanner. JSON/Markdown/offline HTML reports use saved evidence, with no model call or repeated navigation during review.

The package supports fresh observation/candidate IDs; target/backend-node identity checks; document/mutation/input/scroll/viewport staleness checks; typed click/tap, synthetic text, keyboard, scroll, wait, and finish actions; independent completion criteria; bounded feedback waiting; resizing and page-scale emulation; masked screenshots, ARIA, sanitized DOM JSON, offline screenshot marks and coordinate mapping; frame/popup coverage records; runtime/step limits, cancellation, and cleanup. Twenty-six JSON Schemas cover the shared contracts and browser observation/coordinate extensions.

Reports now include actual action arguments/results, browser/fixture versions and runtime origin, configuration, completion checks, policy blocks, request totals/limits, terminal reasons, evidence review gaps, and cleanup. The fixture content hash is recorded for new runs and in the final checkpoint. Startup failures, timeout, cancellation, and incomplete journeys produce factual partial reports. They do not become synthetic abandonment diagnoses.

## Acceptance scope

| Checks | Count | Verified behavior |
|---|---:|---|
| Phase 2 policy/coordinates | 20 | Unknown/foreign origins, namespaces, endpoints, operations, payloads, unsafe paths, upgrades, and stopped sessions rejected; coordinate scaling/offsets and out-of-bounds rejection |
| Phase 2 browser/lifecycle | 14 | Healthy forms; all defect variants; delayed feedback; keyboard focus/zoom; stale identical-node replacement; resizing; raw-text/order denial; popup closure; cancellation; step/runtime ceilings; three profile demos; startup-failure reporting |
| Relevant Phase 1 report/CLI regressions | 15 | Blocked/malformed configuration reports, secret omission, offline downloads, immutability, unexecuted terminal reports, loopback entry point |
| Relevant Phase 1 contract regressions | 17 | Candidate identity, action limits, evidence paths, denominators, route safety, report/review consistency |
| Relevant Phase 1 fixture regressions | 17 | Fixture states, account/reset isolation, integration mocks, validation, order rejection, page/assets, sentinel control |

The 34 Phase 2 checks and 49 relevant regression checks were merged from their latest recorded results. Passing configurations and Phase 0 model/browser scenarios were not repeatedly run.

Each accepted browser scenario ran mandatory startup protection probes against an independent local sentinel. Those probes exercised direct proxy denial, an order operation disguised as GET, redirect denial before following, image/iframe/fetch/beacon requests, WebSockets, and service-worker registration. Unknown browser destinations and unsafe operations were blocked before upstream effects. Across **all 43 saved lifecycle reports, including unsuccessful attempts, sentinel requests total zero and seeded sentinel data stayed unchanged.** This proves only the tested owned-fixture boundary.

Request ceilings were checked against gateway measurements and independent fixture arrival timestamps. All accepted scenarios stayed within two requests per second and one concurrent upstream request for the example policy. Teardown checks confirmed that local fixture/proxy/sentinel services stopped, the owned namespace was reset, and each temporary browser profile was removed. The Playwright runtime's existing `.links` cache metadata is not a run profile and remains intact.

## Healthy profile results

These are deterministic broker demonstrations, not human usability measurements or autonomous cognitive agents.

| Profile | Actions | Observations | Fixture requests | Peak RPS / concurrency | Total duration | Criteria |
|---|---:|---:|---:|---|---:|---|
| Enterprise evaluator, mouse | 4 | 7 | 7 | 2 / 1 | 6.203 s | Passed |
| Impatient mobile, touch | 6 | 9 | 7 | 2 / 1 | 6.172 s | Passed |
| Keyboard/low vision, keyboard + page scale | 9 | 12 | 7 | 2 / 1 | 6.157 s | Passed |

Browser version was Chrome **153.0.8010.53**. The mobile path scrolled to discover controls and tapped them. The keyboard path used actual Tab/Enter navigation without a mouse fallback. The focus-trap scenario recorded unchanged focus under Tab/Escape. Delayed feedback required at least the fixture's 2.5-second delay; dead-button clicks produced no application transition. Generic validation produced its vague error before a declared synthetic correction. Hidden shipping appeared at review rather than the initial product view.

The saved desktop checkout image was visually reviewed: input contents are masked and surrounding labels/buttons remain readable. No new browser session was launched for that review. Accessibility output is available as raw axe evidence; it has not been turned into a compliance claim or a calibrated UX finding.

## Attempts, repairs, and retained evidence

Construction finished before the initial consolidated suite. Static JavaScript syntax passed once. Three initial lint findings were corrected and only affected files rechecked; subsequently changed broker/report/export files also passed targeted lint.

| Attempt | Checks | Pass / fail | Purpose |
|---|---:|---|---|
| Initial boundary suite | 82 | 69 / 13 | Browser scenarios stopped at a shared Playwright event callback issue; successful policy/regression checks retained |
| Browser-only repair 1 | 13 | 0 / 13 | Reached startup protection probes; service-worker check expected a thrown error rather than Playwright's empty registration result |
| Fail-fast repair 2 | 1 | 0 / 1 | Healthy path identified screenshot caret hiding leaving an empty input `style` attribute; sanitized drift metadata retained |
| Fail-fast repair 3 | 1 | 1 / 0 | Original caret/animation state preserved while masking input; healthy form/evidence/axe/teardown passed |
| Remaining browser repair 4 | 12 | 12 / 0 | Healthy scenario deselected; remaining browser cases passed |
| Terminal-report review | 3 | 3 / 0 | New missing-browser path plus affected cancellation/timeout assertions; specific safe reasons and complete partial exports |

The callback fix wraps set operations in ordinary functions accepted by Playwright. The service-worker check verifies the absent registration, zero registrations, and zero sentinel effects. Capture no longer applies caret hiding that could alter the input's attribute state. Snapshot drift remains a hard rejection rather than silently using uncertain candidates. Every unsuccessful attempt received a retained partial report; unfavorable evidence was not overwritten.

No entire passing suite was repeated. The final terminal review was justified by a report defect discovered while reviewing failed attempts. Merging XML and generating this checkpoint read saved data only. Phase 0 was not rerun, and no model or external website was used.

## Evidence links

- [Merged checks](../artifacts/phase2/validation.xml) and [structured checkpoint](../artifacts/phase2/validation.json).
- [Initial suite](../artifacts/phase2/validation-initial.xml), [repair 1](../artifacts/phase2/validation-repair-1.xml), [repair 2](../artifacts/phase2/validation-repair-2.xml), [repair 3](../artifacts/phase2/validation-repair-3.xml), [repair 4](../artifacts/phase2/validation-repair-4.xml), [terminal-report checks](../artifacts/phase2/validation-terminal-reports.xml).
- [Mouse report](../artifacts/phase2/runs/2c2625a0-d23f-4481-9a3d-14778f01764c/report.html), [mobile report](../artifacts/phase2/runs/3038617b-04b6-4b7a-99b0-81c3b0360f3c/report.html), [keyboard report](../artifacts/phase2/runs/2574e908-5191-4a52-bbaf-8340d5874366/report.html).
- [Specific startup failure](../artifacts/phase2/runs/5f8dcbe2-b513-4807-8c30-c1e905449fca/report.md) and [runtime timeout](../artifacts/phase2/runs/01bf885b-e7d0-46ab-822f-c08ecbe1d49b/report.md).
- [Visually reviewed masked checkout screenshot](../artifacts/phase2/runs/27e38402-fa29-4899-9d77-d5757c912bde/evidence/6c6092f3-bbeb-4aba-ba6f-0b00fc117e80.png).

Each report's adjacent `evidence/` contains observations, masked PNGs, SVG marks, sanitized DOM JSON, ARIA text, ordered actions, network records, independent arrivals, startup checks, configuration, completion, and cleanup review. `accessibility.json` exists for scenarios that requested axe inspection. Artifacts are local and ignored by Git; this document preserves the reviewed result.

## Remaining scope

No required work remains for the supported Phase 2 fixture gate. The following restrictions stay enforced:

- Docker/Podman are unavailable. Browser hooks plus a proxy are not an OS/container sandbox and do not justify arbitrary application URLs, alternate clients, or untrusted generated code. External replicas and generated Python remain disabled.
- Frames, popups, shadow roots, and downloads are recorded as coverage gaps; there is no claim that agents can act inside them.
- Installed Chrome can update independently. A dedicated pinned Chromium distribution remains a reproducibility improvement deferred from Phase 0.
- axe signals, keyboard navigation, and page scale do not simulate real assistive technology or certify accessibility.
- Autonomous planning, cognitive patience, UX detectors, cohort orchestration, durable telemetry, calibrated reports/heatmaps, and the dashboard remain their later phases. Existing run reports are correctly marked `partial` for that reason.

**Next:** Phase 3, the single autonomous persona and isolated tool interface. Establish the stronger code-worker boundary before executing generated Python.

## Recorded phase-boundary commands

```powershell
& '.venv\Scripts\python.exe' -m pytest tests\phase_02 tests\phase_01\test_reports_and_cli.py tests\phase_01\test_contracts.py tests\phase_01\test_fixture_api.py --junitxml=artifacts\phase2\validation-initial.xml --tb=short -q
& '.venv\Scripts\ruff.exe' check frictionlab tests\phase_02 scripts\setup_axe.py
node --check frictionlab\fixtures\web\app.js
```

Repair commands selected only the affected browser cases, then the specific terminal-report cases. `python -m scripts.record_phase2_validation` merges stored evidence; it does not launch tests or browser sessions. Use the demo command in `phase2-browser.md` for a separately requested demonstration.
