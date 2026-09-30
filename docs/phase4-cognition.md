# Phase 4 — Evidence-grounded synthetic friction

The `behavioral` command adds deterministic cognitive accounting to the Phase 3 single-persona runner. It still accepts **only the bundled disposable local fixture**. No deployed or arbitrary staging website is contacted; generated Python, external integrations, vision, and autonomous cohorts remain disabled. The existing Playwright/browser-use broker controls every action and captures masked evidence. smolagents chooses actions through typed tools; the cognitive layer never gives it raw browser/network access.

```powershell
& '.venv\Scripts\python.exe' -m frictionlab behavioral --persona impatient_mobile --journey checkout_review --variant dead_button
& '.venv\Scripts\python.exe' -m frictionlab behavioral --persona impatient_mobile --journey checkout_review --variant healthy
```

The command uses the local pinned llama.cpp/Qwen model and no paid service or key. The Phase 4 acceptance harness also has a deterministic observed-control model so exact patience arithmetic and a matched defect/healthy journey can be checked without relying on variable model choices. Those harness decisions are labeled as such; they do not establish local Qwen success on every defect or human behavior fidelity.

`configs/cognition.json` is the versioned local policy. Each profile starts with its `patience_initial` and multiplies base penalties by its configured friction weights. One browser-confirmed action can add at most one primary friction event. Repeated planner attempts on the same visible state/control do not add a second UX penalty. Independent goal milestones provide a small, bounded credit once each. Every ledger row records exact before/delta/after arithmetic, action ID, grounded event IDs, application time, inference time, and explicit zero queue/behavioral delay when those clocks are not measured. The policy file's SHA-256 and version are recorded for reproducibility.

Detectors examine only saved before/after observations and trusted action results:

| Detector | Required observable signal |
|---|---|
| Dead interaction | A grounded control click has no visible result within the broker's bounded feedback window |
| Unclear validation | New visible generic feedback fails to identify a correction |
| Repeated failed correction | A correction is entered and the same control still produces validation feedback |
| Navigation loop | A prior semantic page state returns after a different state |
| Loading failure | A bounded wait ends with the same visible pending state |
| Keyboard trap | Repeated Tab/Shift+Tab/Escape in a visible dialog leaves focus and state unchanged |

Navigation-loop detection excludes scrolls and information-dialog open/close transitions. The behavioral planner also removes an information-only dialog opener from its future candidate list after the dialog has been read, while retaining the facts it displayed. This addresses a saved real-model attempt that repeatedly reopened delivery information; the original timed-out report and its two invalid navigation-loop events remain preserved and are explicitly excluded from UX conclusions.

Events carry action and observation IDs, confidence, the observed control, a factual description, and saved evidence references. They are hypotheses about this controlled fixture's interface, not human UX measurements. Protection-blocked actions, agent/grounding errors, provider failures, model timeouts, and mocked integration events never spend patience. A delayed application response that resolves successfully remains application time, not model time or a loading failure.

When a confirmed event drops patience to zero before independent completion, the tool broker stops further actions. Normal browser teardown captures a final DOM/accessibility snapshot and masked screenshot. A first-person synthetic explanation links the terminal observation and the exact event IDs; a deterministic evidence template is used if optional wording generation fails or proposes unsupported text. The report classifies the outcome as `abandoned_patience` with an eligible denominator of one. Infrastructure/protection failures remain in their own outcome categories with no abandonment diagnosis.

Every run exports immutable `report.json`, `report.md`, and self-contained offline `report.html` under `artifacts/phase4/runs/<UUID>/`, plus `friction-events.json`, `patience-ledger.json`, `cognitive-state.json`, browser observations/actions, protection checks, and model decisions when available. Review reads stored evidence without revisiting the fixture. Reports remain **partial** because cohort aggregation, calibrated findings, heatmaps, and prioritized remediation are later phases. The CLI prints the report directory and terminal outcome.

Phase 4 acceptance passed after construction: **109 distinct checks** now pass, including a seeded defect, matched healthy completion, delayed success, model faults, protection, dialog attribution, and report checks. One repaired local-Qwen defect run also reached the dead button and produced a supported synthetic abandonment; its earlier timed-out attempt is retained. Raw unfavorable outcomes remain in separate directories; passing matched browser scenarios were not repeated to improve a rate. The [validation record](phase4-validation.md) explains the deterministic action harness, real-model attempt, and limits. Full Phase 3's OS/container generated-code gate is still unmet, so this phase does not enable arbitrary replica URLs.
