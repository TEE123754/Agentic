# Phase 10 validation record

## Declared gate

Installable local CLI and bounded BYOK transports, verified using mocked provider responses on an ephemeral Linux runner. Live account eligibility, real-model behavior and clean Windows/macOS archive installation are unverified. No production/staging URL support or public package publication is included.

## Acceptance

Build `d50bd06`: [consolidated run 36892800838](https://github.com/TEE123754/Agentic/actions/runs/36892800838) passed **48/48** checks in 33.21 seconds, plus isolated installed-wheel acceptance. The batch covered new Phase 10 configuration/transports/budgets/secret handling and affected Phase 1 configuration checks. Installation loaded the package from site-packages outside the checkout, used init/validate/doctor, and ran a real owned-fixture browser probe with bundled axe and terminal reports. No large model/runtime downloads occurred.

The real cloud adapters used httpx MockTransport. Fixed Groq/Gemini endpoints and headers, explicit consent, missing keys, redirects, 401/429/503, timeout, response/input size, runtime, retry/request budgets and excessive usage were checked. Secret values were not printed or stored; failed inference produced infrastructure outcomes without a synthetic abandonment diagnosis. Two real fixture cohorts used deterministic mocked decisions through the actual CloudPlannerModel: defect abandoned, healthy completed, one seeded finding resolved and completion delta was +1. This is integration evidence, not a live-model quality score.

Build `41cef5e`: [installed-asset navigation follow-up 36893880901](https://github.com/TEE123754/Agentic/actions/runs/36893880901) verifies the installed landing page and bundled sample report from a fresh workspace; passed. The installed page links to the bundled sample, its setup-guide target exists, and review makes zero HTTP requests. Only installation acceptance is rerun; the 48 passing checks are retained.

Build `3f00516`: [affected cohort gate 36894867219](https://github.com/TEE123754/Agentic/actions/runs/36894867219) passed **2/2** in 42.77 seconds (19 unrelated cases deselected). Code review had found invalid inference configuration could raise before cohort reporting. Settings are now frozen at submission; rejected settings create a factual terminal report with zero executed sessions and no transport/navigation. Existing matched BYOK cohorts still pass. Final source import ordering was linted without runtime changes. Overall: **49 distinct passing pytest cases**, plus installed CLI/browser/navigation acceptance. Phase 10 checklist is complete for this declared gate.

## Offline artifact review

Downloaded wheel/source SHA256 values matched the build manifest. Wheel contains 162 files and the source archive 162 members. Configuration, synthetic fixtures, axe script/licenses, viewer, product page and guides were present. Archives contain no local inference config, environment files, run artifacts, weights or Git history. Sizes: wheel 898,210 bytes and source 934,654 bytes for the first build.

Both audited cohort reports were ready with valid finding references and no missing evidence. Protection records show zero sentinel requests and unchanged sentinel data. The defect screenshot and remediation were inspected offline. Missing-key report was produced before any navigation; quota-fault report recorded inconclusive agent failure with no abandonment diagnosis. A byte-level offline scan of all 151 saved evidence files, including DuckDB, found no synthetic key marker.

## Remaining outside the declared gate

- Supply a user-owned free-account key and confirm current account/model eligibility before any optional live smoke. No real key or cloud smoke was used here.
- Live planner behavior, broader persona coverage and calibrated human churn predictions remain unverified.
- Public GitHub visibility, GitHub Release/PyPI publication and hosted landing page are separate release steps. The downloads are development workflow artifacts and expire on GitHub after 14 days; local copies and source remain available.
- Phase 11 performs consolidated release/pilot validation, including further platform/license review and any declared scope changes. External replicas stay blocked until proven isolated.


## Latest retained downloads

Code build `3f00516` is retained locally under `dist/` and in the final workflow artifact. Final wheel: 898,472 bytes, SHA256 `8f60fb78611874b0168353a10b636b0ae278329cfaf63a571ab5cff3240d376f`. Source archive: 934,896 bytes, SHA256 `107275a271cb982f97202990c503d4bee8d60f88bd2cc33d2de41a738b81db85`. These immutable build snapshots include the checkpoint as it stood at build time; this validation record and the main-branch implementation plan record the final gate outcome.
