# Phase 4 acceptance record

**Recorded:** September 30, 2026, Asia/Kuala_Lumpur. Artifact timestamps use UTC.

**Result:** The bundled-fixture cognitive gate passed. The initial post-construction batch passed 104/104 checks. Five new checks from final evidence review bring the merged latest result to **109/109 distinct checks passing**. One raw harness-assumption failure remains retained and was resolved by an affected-only rerun. No passing matched browser journey was repeated. Two separate real local-Qwen defect attempts are also preserved: one timeout with invalid detector events and one repaired evidence-backed abandonment.

## Scope and acceptance method

Only the owned disposable storefront was used, with synthetic accounts, local integration mocks, fixed-upstream proxy, and independent local disallowed-service sentinel. The matched acceptance pair used a deterministic smolagents `Model` harness selecting current semantic candidates, making patience arithmetic reproducible. Separately, the production `behavioral` CLI ran twice with the local pinned Qwen/llama.cpp planner. A single repaired Qwen success establishes this integration path on the fixture; it is not a reliable completion rate or human-behavior calibration.

The consolidated batch included 16 Phase 4 checks, 36 relevant Phase 3 model/tool checks, 15 report/CLI checks, 17 contract checks, and 20 policy checks. Five final-review checks raised the Phase 4 subtotal to 21 and the merged total to 109. Ruff passed for changed Python files. Pydantic exported 31 schemas. The batch ran after construction; failed/new checks alone were selected afterward. No Phase 0, Phase 3 healthy-model, or complete regression suite was repeated.

| Retained batch | Selected checks | Failures | Why it ran |
|---|---:|---:|---|
| `validation-initial.xml` | 104 | 0 | One consolidated phase-boundary pass |
| `validation-repair-1-event-chain.xml` | 1 | 0 | New check that diagnosis links all recorded friction events |
| `validation-repair-2-boundaries.xml` | 2 | 1 | Zero-weight arithmetic passed; guard harness incorrectly expected fixture controls in grounded candidates |
| `validation-repair-3-guard.xml` | 1 | 0 | Corrected guard check verified protected controls cannot be selected and blocked actions do not spend patience |
| `validation-repair-4-dialog-attribution.xml` | 2 | 0 | One new dialog-cycle guard plus affected navigation-loop detector check |
| `validation-repair-5-information-memory.xml` | 1 | 0 | Behavioral memory kept read facts and hid the information-only opener after closing |

The [merged XML](../artifacts/phase4/validation.xml) contains the latest result for each distinct check. The [structured checkpoint](../artifacts/phase4/validation.json) retains attempt counts, the raw failed harness report, and both real-model outcomes. This aggregation reads saved artifacts only.

## Matched journey evidence

All matched runs used seed 42, the impatient mobile profile, checkout-review goal, and the same fixture build.

| Fixture | Trusted outcome | Actions | Patience | Recorded friction | Saved report |
|---|---|---:|---:|---|---|
| Dead checkout button | `abandoned_patience` | 3 | 55 → 0 | One grounded `dead_interaction`, confidence 0.94 | [Offline report](../artifacts/phase4/runs/4c5b90ab-630d-4444-b8c8-9f44718c56f1/report.html) |
| Healthy | `completed` | 5 | 55 → 63 | None; two independently verified milestones credited | [Offline report](../artifacts/phase4/runs/7bb91b99-f9a3-46dd-a1e6-fbfe8eb202f8/report.html) |
| Delayed feedback | `completed` | 5 | 55 → 63 | None, despite ≥2.5 seconds of application delay | [Offline report](../artifacts/phase4/runs/1a51736c-0f7b-49db-ac01-ae58e59c7002/report.html) |

The dead-button run scrolled twice, clicked the observed **Start checkout** control, waited through the broker's bounded feedback window, and saw no visible change. Its final screenshot still shows the product and checkout button. The ledger applied one profile-weighted, clamped penalty of −55 and then stopped tool execution. The first-person diagnosis cites that event's ID and a distinct terminal observation with screenshot, DOM, and accessibility evidence. It does not claim a human user left. The healthy final screenshot shows Order review and “No order has been placed”; no payment or external dispatch occurred.

Two separate negative runs raised model timeout and invalid-output faults before any browser action. Both retained detailed partial reports with `inconclusive_agent_failure`, eligible denominator zero, no friction events, and no abandonment diagnosis. The delayed fixture's 2.5-second-plus response was counted as application time and ended in verified success, so it did not become a false loading or model-time penalty. Unit checks verified exact detector arithmetic, repeated-correction evidence, navigation-loop history, keyboard-trap repetition, duplicate retry exclusion, zero profile weight, one-time milestone credit, provider-error exclusion, and template fallback after optional wording failure.

### Real local-Qwen defect attempt and repair

The first actual local-Qwen run [timed out](../artifacts/phase4/runs/88d69f16-357d-44bd-8061-cd6b447a32e2/report.html) after 17 model decisions, repeatedly opening and closing the delivery-information dialog instead of advancing to checkout. The original detector recorded two `navigation_loop` events for these dialog transitions. Saved action/observation review showed they were **false UX attributions**. The immutable report made no abandonment diagnosis and classified the session as `timed_out`; its two friction events are explicitly rejected from UX conclusions. Sentinel traffic was zero and its state unchanged.

The detector now excludes scrolls and dialog open/close transitions from navigation-loop penalties. After an information-only dialog has been read, behavioral memory retains its visible facts and removes its opener from later candidates. Targeted detector and browser-memory checks passed. A fresh actual local-Qwen run [reached the dead checkout button](../artifacts/phase4/runs/13e8b5a3-e09f-487a-8ee1-c6432d63c4ae/report.html) in six model decisions, recorded exactly one `dead_interaction` event at confidence 0.94, spent 55 → 0 patience, and stopped with a linked first-person diagnosis and terminal screenshot. Inference took 75.186 seconds; application actions took 5.312 seconds. It made no order or external dispatch, sent zero sentinel requests, and cleaned up owned resources. This is one repaired success after one unfavorable attempt, not a population rate.

## Protection and offline review

Ten Phase 4 terminal reports, one protected-control browser probe, and one information-dialog browser probe report were preserved. The ten include the unsuccessful guard-harness attempt and first real-Qwen timeout. The harness failure report honestly records `agent_error` before any action because the fixture reset control was absent from model-visible candidates. The later direct broker probe confirmed an unavailable candidate is blocked and charged zero patience. A second trusted executor check rejects fixture reset/variant clicks even if a caller somehow supplies such a control. The passing deterministic defect, healthy, and delayed scenarios were not rerun for these repairs.

Ten initialized sentinel reports across Phase 4 runs and both targeted browser probes show **zero requests and unchanged seeded state**. The separate preflight rejection started no sentinel/browser/model and made zero target requests; this is not counted as a tested sentinel. No external website, generated Python, vision inference, real transaction, or live integration was used. Browser/proxy/services, owned Chrome profiles, and synthetic run data were cleaned up.

Every terminal run wrote `report.json`, `report.md`, and self-contained offline `report.html`. Saved-review aggregation validated report contracts, all visual/friction/diagnosis references, and ledger-to-event IDs; no referenced file was missing. HTML contains no remote script. Deterministic dead/healthy and repaired-Qwen terminal screenshots were visually inspected from saved evidence without another browser run. Reports remain `partial` because cohort aggregation, calibrated findings, heatmaps, and prioritized frontend remediation belong to later phases.

## Limits and remaining work

This gate establishes synthetic behavior on one known fixture under a controlled action harness and one repaired real-Qwen attempt. Profile weights are design settings, not empirically measured human patience; false-positive rates, repeated-seed model reliability, and cross-site transfer remain unmeasured. Broader local fixtures and human review are needed before calling these diagnoses predictive. Real assistive technology and vision localization remain unvalidated.

The full Phase 3 generated-code/container gate is still unmet because this host lacks Podman/Docker and usable WSL. Only trusted typed-tool fixture execution is enabled; arbitrary staging URLs and generated Python remain blocked. Phase 5 cohorts/DuckDB/recovery and Phase 6 aggregate UX reports, recommendations, and heatmaps are unbuilt. No required work remains in Phase 4's supported fixture gate.
