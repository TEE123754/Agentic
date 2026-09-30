# Implementation status

## Phase 0 — Complete (fixture-only feasibility)

**Date:** September 29, 2026.

**Delivered:** Hardware inventory; project-local environment and `uv.lock`; dependency/license manifest; hash-verified llama.cpp b11247 and Qwen3-4B Q4_K_M weights; bounded local planner configuration; optional disabled vision path; bundled storefront, proxy, and disallowed-service sentinel; browser-use read-only DOM adapter using the same target as Playwright; observed-candidate action registry; memory sampling; detailed offline reports; browser/generated-code isolation design; setup and execution instructions.

**Acceptance check:** One bundled Phase 0 scenario after construction. Initial lint identified five findings; they were fixed and only the affected file was rechecked. The browser/model scenario passed on its first execution; no full-suite or repeated browser runs were performed.

**Result:** 16/16 checks passed. Qwen selected Start checkout; Playwright reached Order review. Sentinel received zero requests. Service workers absent. Model startup 4.19 s, decision 8.55 s, complete scenario 16.84 s. Peak combined monitored RSS 5.311 GiB. All owned runtime processes/services closed without reported cleanup errors.

**Evidence:** [Detailed report](../artifacts/phase0/20260929T091343.937322Z/report.md), [offline HTML](../artifacts/phase0/20260929T091343.937322Z/report.html), [validation review](phase0-validation.md).

**Known limitations:** Podman/Docker unavailable; no OS/container isolation claim. Only bundled local fixtures are allowed. No generated Python executes. Installed Chrome used after dedicated Chromium CDN timeouts. SmolVLM configured but not installed/downloaded/validated. Single-page, one-click integration does not establish UX detection, persona calibration, or broader navigation quality.

**What remains for Phase 0:** No required gate tasks. Optional dedicated-browser reproducibility and vision measurement remain deferred.

**Next after this gate:** Phase 1 contracts/configuration/fixtures, now completed below. Phases 2–3 must implement and validate container/network and generated-code boundaries before enabling arbitrary replica URLs or code agents. Do not treat the Phase 0 proxy as that boundary.

## Phase 1 — Complete (foundation and controlled fixtures)

**Date:** September 29, 2026.

**Delivered:** Importable `frictionlab` package and loopback startup command; Pydantic configuration, browser/action/evidence/protection/report contracts; 24 JSON Schemas; three profiles, three observable journeys, environment manifest and example run; offline reference resolution and configuration hash; six storefront variants; unique synthetic accounts; deterministic run-scoped reset; six local integration mocks and a rejected sentinel control; configuration review API; disabled browser execution with automatic JSON/Markdown/offline HTML partial reports; phase-scoped acceptance tests and setup/API guide.

**Acceptance:** 78 distinct checks passed. Construction preceded the initial consolidated pass. Initially 52 passed and 25 stopped at setup because the tripwire blocked Windows' event-loop socket pair. After correcting that harness issue, only the 25 affected checks were rerun, plus one new guard check. Ruff passed after two targeted style repairs; JavaScript syntax passed once. No Phase 0, browser, model, or full-suite repeat occurred.

**Protection result:** Configuration rejection, mock integrations, synthetic order review, and reset were validated with application connections/DNS denied in the test process. Standard-library internal socket pairs are explicitly permitted. No external website was contacted. This is not network/container protection validation; browser execution remains disabled.

**Evidence:** [Validation review](phase1-validation.md), [merged checks](../artifacts/phase1/validation.xml), [structured checkpoint](../artifacts/phase1/validation.json), [sample partial report](../artifacts/phase1/sample/92ae9513-2163-455d-9b5b-d41e68f5bbf9/report.md), [Phase 1 guide](phase1-foundation.md).

**What remains for Phase 1:** No required work. Rendered browser behavior and transport protection belong to Phase 2. In-memory data, lack of OS/container isolation, and absence of autonomous UX analysis remain explicitly documented limitations.

**Next:** Phase 2 browser observation/execution and replica-only traffic. Do not enable external targets or generated code based on Phase 1's configuration checks.

## Later phases

Phase 4's owned-fixture gate is complete below; phases 5–10 have not started. Phase 3's typed-tools fixture scope passed after repairs; its full generated-code/container gate remains unmet.

## Phase 2 — Complete (owned-fixture browser/proxy gate)

**Date:** September 29, 2026.

**Delivered:** Playwright broker and same-target browser-use/CDP grounding; typed observe/act/verify tools; fresh candidate/document identity and stale-element rejection; viewport/touch/keyboard/page-scale support; independent completion criteria; masked screenshots, sanitized DOM/ARIA, offline marks and coordinate mapping; focus/validation/frame/network evidence; endpoint/payload-aware fixed-upstream gateway and independent sentinel controls; request/concurrency/step/runtime limits, cancellation and cleanup; pinned offline axe-core scanner/provenance/licenses; deterministic browser demo; 26 contract schemas; detailed terminal reports and validation guide.

**Acceptance:** 83 distinct passing checks: 34 new Phase 2 checks and 49 relevant regressions. Construction preceded the initial consolidated pass. Browser callback, service-worker check, and screenshot caret-state issues were repaired with browser-only/fail-fast checks. After successful acceptance, report review added a specific startup-failure reason and targeted terminal-report checks. Passing full suites, policy checks, Phase 0, model calls, and JavaScript checks were not repeated. Lint passes.

**Protection result:** Across all 43 retained lifecycle reports, including failed attempts, the independent sentinel received zero requests and its seeded data stayed unchanged. Accepted sessions enforced the example two-request/second and one-upstream-concurrency ceilings and cleaned up their owned services, synthetic data, and temporary profiles. Supported scope is the bundled fixture/browser/proxy boundary only; external replicas and generated code remain disabled.

**Observed demos:** Mouse, mobile touch, and keyboard/page-scale paths all completed independent checkout-review criteria. Known defects produced saved validation/no-change/delay/cost/focus evidence; they were not labeled as human churn. Stored desktop screenshot was visually reviewed with input masking intact.

**Evidence:** [Validation review](phase2-validation.md), [structured checkpoint](../artifacts/phase2/validation.json), [browser guide](phase2-browser.md), [mouse report](../artifacts/phase2/runs/2c2625a0-d23f-4481-9a3d-14778f01764c/report.html), [mobile report](../artifacts/phase2/runs/3038617b-04b6-4b7a-99b0-81c3b0360f3c/report.html), [keyboard report](../artifacts/phase2/runs/2574e908-5191-4a52-bbaf-8340d5874366/report.html).

**What remains for Phase 2:** No required tasks in its supported fixture gate. OS/container isolation is unavailable; frame/popup/shadow-root/download actions and real assistive technology are unsupported. Installed Chrome is recorded but unpinned. These limits remain explicit and must be addressed before expanding execution scope.

**Next:** Phase 3 single autonomous persona. Validate the stronger code-worker boundary before executing generated Python. Cognitive runtime, detectors, orchestration, durable telemetry, calibrated UX reports/heatmaps, and dashboard remain later work.

## Phase 3 — Typed-tools fixture scope verified; full phase partial

**Date:** September 30, 2026 (Asia/Kuala_Lumpur; raw artifact timestamps use UTC).

**Delivered:** Locked smolagents 1.26.0; shared owned llama.cpp/Qwen adapter with checksum, token, request, and sampled memory limits; ToolCallingAgent with only trusted browser/final tools; three profile prompts; isolated bounded persona memory; viewport/keyboard observation filtering; declared synthetic text references; action/tool/step/runtime/retry ceilings; independent goal assertions; fail-closed generated-code mode; autonomous CLI; detailed decision/terminal reports; acceptance harness and guide.

**Acceptance:** 100 distinct checks pass: 48 Phase 3 checks and 52 relevant report/contract/protection regressions. Construction preceded the initial consolidated pass. That batch passed 85/88 checks; all three initial healthy model journeys failed the declared 3/3 threshold. Repairs reran only affected/new checks. Passing enterprise/mobile browser-model executions were not repeated; mobile's corrected privacy assertion was reviewed from saved evidence only. The final three configuration-rejection checks ran offline. Changed Python files pass Ruff.

**Results:** Latest independently verified outcomes cover all three profiles: enterprise delivery information in one model-selected action, mobile checkout review in 16, keyboard checkout in 11. Ten real healthy attempts across successive implementation versions produced three completions; all failures remain recorded. These are capability checks, not calibrated conversion rates. Reports record 84 model decisions. The keyboard success used 153.096 seconds of model processing, 2.595 seconds of application processing, and 5.163 GiB peak sampled model RSS.

**Protection/report review:** All 19 terminal outcomes exported detailed JSON, Markdown, and offline HTML reports. Three preflight rejections started no browser/model/sentinel and made zero target requests; the other 16 retained reports show zero sentinel requests and unchanged sentinel data. Owned browser profiles/services and the shared model owner were cleaned up. Review used stored evidence, including a visually inspected mobile terminal screenshot showing Order review and no order placed. No external website, generated Python, or vision model was used.

**Targeted fixes:** Independent completion ends the agent immediately; unverified finish is unavailable. Real scroll movement counts as progress. Keyboard actions require applicable grounded focus, historical memory excludes stale control/dialog markup, and Escape requires a current dialog. The native model cache is capped at 512 MiB; credential/tool environment overrides are stripped; memory termination is classified as infrastructure failure. Invalid configuration, selections, and agent settings now export preflight reports without execution.

**September 30 completion attempt:** Constructed an OCI-side generated-code process, a rootless Podman launcher with immutable local image ID and no network/host mounts, a bounded stdio action channel to the trusted broker, a pinned-base `Containerfile`, and the `smolagents.CodeAgent` source adapter. The runner requires a matching host/image boundary gate before model or browser startup. Twenty new offline worker/adapter checks and two existing blocked-mode guards pass; targeted lint passes. This is source-level construction, not a validated sandbox. A fresh host check still found no Podman, Docker, or installed WSL.

**Remaining for Phase 3:** Provision a free rootless runtime, build/inspect the pinned image, pass one real-container escape/IPC/limit/cleanup batch on that exact host/image, and review one owned-fixture CodeAgent journey/report. The current proxy and offline checks do not establish this boundary. Generated Python stays disabled, and full Phase 3 remains partial. No other required work remains in the supported typed-tools fixture scope. Broader replica support, optional vision, real assistive technology, cohorts, heatmaps, and dashboard remain separate/deferred work. [Worker checkpoint](phase3-code-worker.md).

**Evidence:** [Acceptance review](phase3-validation.md), [structured results](../artifacts/phase3/validation.json), [merged checks](../artifacts/phase3/validation.xml), [autonomous guide](phase3-autonomous.md), [mobile report](../artifacts/phase3/runs/204a3c49-dca9-4e48-a473-aeaf25fb46a2/report.html), [keyboard report](../artifacts/phase3/runs/f192ad61-4aba-456b-b1e7-aab860d3b423/report.html), [enterprise report](../artifacts/phase3/runs/8271c88e-eaeb-4ee2-94a0-ef92a15fa963/report.html).

## Phase 4 — Complete for the owned-fixture cognitive gate

**Date:** September 30, 2026 (Asia/Kuala_Lumpur).

**Delivered:** Versioned deterministic friction settings; evidence-backed detectors for dead interaction, unclear validation, repeated failed correction, navigation loop, loading failure, and keyboard trap; bounded profile-weighted patience ledger with milestone credit and retry deduplication; first-person evidence-template diagnosis at patience exhaustion; an opt-in Phase 4 behavioral runner/CLI; and detailed terminal report contracts/sections. Infrastructure, protection, and model failures remain separate outcomes.

**Acceptance check:** One consolidated post-construction batch passed 104/104 checks. Five new final-review checks brought the merged total to **109/109**. A protected-control harness assumption failed once, was repaired, and only that affected check was rerun. Dialog-attribution and information-memory repairs were also checked with targeted new/affected checks. Original raw failures/reports remain. Passing matched browser journeys were not repeated.

**Result:** The seeded mobile `dead_button` journey abandoned at 55 → 0 patience after a grounded dead click, with confidence 0.94, final evidence, and a first-person synthetic explanation. The matched healthy checkout completed in five actions with no friction; delayed feedback completed without a false loading failure. Timeout/invalid model output stayed inconclusive and did not count as churn. These matched actions used a deterministic semantic-control smolagents harness. Two additional real local-Qwen defect attempts were retained: the first timed out after repeatedly reopening delivery information and generated two false navigation-loop events without an abandonment claim; after detector/memory repairs, the second reached the dead button in six model decisions and produced one valid dead-click abandonment. Neither outcome is a calibrated success rate.

**Protection/report review:** Ten Phase 4 terminal reports, one protected-control probe, and one information-dialog probe report were retained. Ten initialized sentinel reports recorded zero requests and unchanged data; the unexecuted preflight rejection made zero target requests. Report exports and evidence links resolved. Saved dead/healthy/repaired-Qwen screenshots were reviewed offline, showing no order or external dispatch. No external website, generated Python, or vision call occurred.

**Known limitations / next:** The gate covers one owned fixture and synthetic profiles, not calibrated human abandonment or robust model performance across seeds. Broader false-positive evaluation and human review remain. Phase 3's source-built OS/container generated-code path is still unvalidated, so external replicas and generated code remain disabled. Phase 5 cohorts/DuckDB/persistence and later aggregate UX reports/heatmaps/dashboard have not started. No required Phase 4 fixture-gate work remains.

**Evidence:** [Validation review](phase4-validation.md), [structured results](../artifacts/phase4/validation.json), [merged checks](../artifacts/phase4/validation.xml), [behavioral guide](phase4-cognition.md), [repaired local-Qwen report](../artifacts/phase4/runs/13e8b5a3-e09f-487a-8ee1-c6432d63c4ae/report.html), [original timed-out Qwen report](../artifacts/phase4/runs/88d69f16-357d-44bd-8061-cd6b447a32e2/report.html), [matched healthy report](../artifacts/phase4/runs/7bb91b99-f9a3-46dd-a1e6-fbfe8eb202f8/report.html).
