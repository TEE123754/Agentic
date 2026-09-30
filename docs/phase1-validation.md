# Phase 1 acceptance and evidence review

**Date:** September 29, 2026. **Result:** Phase 1 complete; 78 distinct checks passed, with no unresolved failures. Browser execution remains disabled.

## Delivered and reviewed

The importable application uses Python 3.12.14, FastAPI 0.141.1, Uvicorn 0.54.0, Pydantic 2.13.5, and HTTPX 0.28.1. pytest 9.1.1 and Ruff 0.16.9 provide acceptance checks. Exact dependencies are locked in `uv.lock`; installed metadata records 116 distributions. All execution/report operations in this phase are local and need no paid provider.

Three behavioral profiles, three observable journeys, one isolated fixture policy, and an example run are available in `configs/`. Twenty-four shared contracts have exported JSON Schemas in `docs/schemas/`. The example represents nine requested sessions; none executes yet.

The storefront includes healthy, generic-validation, dead-button, delayed-feedback, hidden-shipping, and focus-trap variants. Run UUIDs scope synthetic accounts, checkout attempts, integration mock events, and deterministic resets. Only synthetic order review is implemented; real orders are explicitly rejected.

Rejected run/configuration requests generate factual partial reports. Eleven sections include scope, protection checks, cohort counts, trajectories, findings, visual evidence, abandonment, recommendations, comparison, and review limitations. Unavailable evidence is explicitly missing; no UX diagnosis is manufactured. JSON, Markdown, and escaped offline HTML can be downloaded without opening a target website.

## Acceptance results

| Area | Recorded evidence |
|---|---|
| Configuration | Profiles/journeys resolve; nine-session calculation and stable hash; changed seed changes hash; invalid repetition/traffic limits rejected |
| Target protection prerequisites | Production/non-owned origins, credential-bearing origins, URL paths/fragments, unknown dependencies, missing mocks, missing isolation evidence, and allowed/blocked origin overlap all rejected offline |
| Registry integrity | Unknown/escaping/duplicate references and mismatched filenames rejected; missing/malformed/oversized JSON rejected |
| Browser/action contracts | Candidate observation/target identity enforced; bounded tool arguments; arbitrary raw text and unsupported keys rejected; relative-path browser normalization checks |
| Evidence/report consistency | Escaping artifact paths rejected; finding denominators/evidence and outcome totals validated; `ready` requires evidence review; dispositions cannot reference missing findings |
| Fixture API | App creation, health, page/assets, all six variant states, unique accounts, helpful/vague validation, order review, and forbidden order endpoint pass |
| Reset | Removes accounts, checkout attempts, and mock events only in the owned run; preserves other runs and variant; reproduces the initial account |
| Mocks and sentinel control | All six integrations remain local; zero external dispatch/real orders; rejected sentinel attempt records zero delivered requests |
| Terminal report exports | Invalid/blocked/non-object/malformed requests produce reports; pre-navigation failure/cancellation/interruption exports remain factual; all eleven sections and downloads present |
| Secrets and report access | Rejected values omitted from diagnostics; HTML escaped; no report scripts/frames; restrictive HTML content policy; duplicate run ID cannot overwrite report |
| Entry point | Offline validation and failure report creation pass; serve command uses loopback host and rejects privileged ports |
| Network tripwire | Application socket connections, connection helpers, and DNS are denied during acceptance; only standard-library internal socket pairs are permitted for the Windows event loop |
| Static checks | Consolidated Ruff scope passed after two targeted style repairs; JavaScript syntax passed once |

## Attempts and repair

Construction finished before the first suite. The initial consolidated pass collected 77 checks: **52 passed**, while **25 stopped during test setup**. The network tripwire had blocked Windows' standard-library socket pair used internally by the event loop, so those API checks did not reach product code. Startup warnings from that failed event loop initialization are retained in the initial evidence.

The guard was corrected to permit only trusted, internal socket-pair setup on the same thread while continuing to reject application connections and DNS. All 25 affected checks then passed using pytest's last-failed selection; seven already-passed checks in those files were deselected. A newly added guard regression check passed separately. Two lint findings about dictionary construction were repaired, and only the affected files were rechecked. JavaScript, Phase 0, successful configuration/contract tests, and browser/model scenarios were not rerun.

The latest result per check is merged from saved XML; this is evidence processing, not another suite run.

| Evidence | Contents |
|---|---|
| [Initial pass](../artifacts/phase1/validation-initial.xml) | Original 77 checks, including 25 setup errors |
| [Targeted repair](../artifacts/phase1/validation-repair.xml) | 25 affected checks passing |
| [Guard regression](../artifacts/phase1/validation-network-guard.xml) | One additional check passing |
| [Merged acceptance](../artifacts/phase1/validation.xml) | 78 distinct checks, zero unresolved errors |
| [Structured checkpoint](../artifacts/phase1/validation.json) | Counts, attempt history, configuration hash, scope, and limitations |
| [Sample partial report](../artifacts/phase1/sample/92ae9513-2163-455d-9b5b-d41e68f5bbf9/report.md) | Example nine-session configuration blocked before navigation |
| [Offline HTML report](../artifacts/phase1/sample/92ae9513-2163-455d-9b5b-d41e68f5bbf9/report.html) | Same factual report, eleven sections, no remote resources |

Evidence artifacts are local and ignored by Git. This review and `docs/phase-status.md` retain the completion summary independently. The sample was generated from stored configuration after acceptance; it did not start another run or contact a website.

## What remains

No required Phase 1 acceptance work remains. Phases 2–10 have not started.

- Phase 2 must verify actual rendered journeys, click/focus/delay behavior, browser observation/action lifecycle, traffic ceilings, cleanup, and independent transport-level sentinels.
- A manifest declaration and a rejected mock dispatch are not OS/container isolation evidence. Strict external replica execution stays unavailable until the network boundary is implemented and validated; generated Python stays unavailable until Phase 3 isolation passes.
- Fixture storage is in memory and erased on restart. Durable telemetry, recovery, and idempotent report finalization belong to later phases.
- No autonomous cohort, patience simulation, real UX finding, heatmap, human calibration, or dashboard has been claimed by Phase 1 acceptance.

The exit gate is satisfied for the local application/configuration foundation. Startup routing was checked in-process and the command's loopback binding was verified without leaving a server running. No real browser was launched or deployed website tested.
