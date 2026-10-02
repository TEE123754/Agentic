# Phase 11 release validation record

**Status: INCOMPLETE. The release gate is not met.** Construction, recovery repair, installed packaging and evidence review are finished. Real local-model completion and the three-profile real pilot still need to pass. Phase 11 remains unchecked.

## Single consolidated window

Build `83054b4`, [run 36896802260](https://github.com/TEE123754/Agentic/actions/runs/36896802260): **249 passed, 4 failed in 1615.56 seconds**. Clean Python 3.12/uv locked installation, explicit checksum-pinned local resource downloads, wheel/source build, dependency inventory and artifact retention succeeded. The full regression was run once. No resources were downloaded onto the laptop; no provider key, deployed website, real account, publication or hosted execution was used.

Failures:

1. `tests/phase_03/test_autonomous.py::test_healthy_seeded_persona_first_attempt[impatient_mobile-checkout_review]`: independent completion assertions false.
2. `tests/phase_03/test_autonomous.py::test_healthy_seeded_persona_first_attempt[keyboard_low_vision-keyboard_checkout]`: independent completion assertion false.
3. `tests/phase_05/test_cohorts.py::test_interrupted_journal_recovers_once_without_inventing_churn`: recovery report status failed instead of partial; legacy manifest omitted journey definitions and synthesis raised KeyError.
4. `tests/phase_11/test_release.py::test_three_profile_local_release_pilot`: three real local-model defect sessions timed out; audit correctly partial, not ready. Healthy candidate/comparison/export half was never reached.

The real pilot retained five valid enterprise decisions, five valid mobile decisions plus a timed-out request, and four valid keyboard decisions plus a timed-out request. Decision durations were approximately 31–52 seconds; sessions reached the 240-second planner ceiling. Peak shared model RSS was approximately 5.15 GiB and the memory limit was not hit. All three outcomes were `timed_out`, zero eligible UX sessions, no abandonment diagnosis/findings, zero sentinel requests, unchanged sentinel data and factual partial reports. This is a failed performance/completion gate, not a measured abandonment rate or a UX blocker. The enterprise delivery-information regression passed, but does not establish three-profile checkout completion.

## Affected repair window

Build `b01f0a7`, [run 36901248316](https://github.com/TEE123754/Agentic/actions/runs/36901248316): **20/20 affected cohort/audit checks passed in 41.50 seconds**, followed by installed-wheel acceptance. Missing journey definitions now yield an explicit evidence exclusion and partial audit instead of KeyError. Recovery, fresh retry, cancellation, stopped-run reporting, synthesis fault preservation, finding review and directly affected audit integrations passed. No full-suite repeat or model download was performed.

Installed package was loaded from site-packages outside the checkout. Version 0.1.0, init/validate/doctor, installed owned-fixture browser probe, bundled axe, landing-to-sample navigation, zero review HTTP requests, zero sentinel requests, unchanged data and no large downloads were verified. Overall **250 distinct regression cases now pass; three real-model cases remain unresolved**. Repeated affected checks are not added to the distinct count.

## Offline review

The frozen deterministic four-report quality batch still meets its declared fixture thresholds: healthy completion, high-severity precision, seeded-blocker detection and finding-reference validity each 100%; zero inconclusive sessions and zero sentinel traffic. It uses the semantic acceptance harness, not a live model quality measurement. Both saved comparisons show one additional completion and a resolved seeded finding. Dashboard review/download and static viewer import/filter/playback/heatmap checks passed in the consolidated suite.

Reviewed the retained dashboard screenshot, dead-control screenshot, aggregate findings and recommendations. Ready aggregate reports had no missing finding references and recorded zero sentinel requests/unchanged data. The observed inert Start checkout control supports immediate visible feedback, a clear disabled state or a recoverable error as remediation. Real-model timeout audits were reviewed separately and make no UX recommendation from those failures.

Wheel/source contents and checksum manifests were inspected: configurations, profiles, synthetic fixtures, axe license files, viewer/site and release guide present; weights, runtime, environment files, local inference configuration, evidence and Git/virtual-environment data absent. Initial archives contain 164 members each. Latest repaired snapshots are retained in ignored local `dist/`: wheel 907,950 bytes, SHA256 `3a5401d48ef310c7ef23de319e686c979ae37bd1056933cf35b7329079899b8f`; source 942,930 bytes, SHA256 `170cb60411629cf4ba4b285c626938642996a865b7ed6d41fd2a63f243f664e1`. They are development release candidates, not a validated/public release. These immutable build snapshots precede the final validation documents and illustrative partial examples; rebuild after the remaining gate passes.

The clean runner recorded 140 distributions. Direct dependency versions match the declared lock resolution, including Playwright 1.63.0, browser-use 0.13.10, smolagents 1.26.0, DuckDB 1.5.5, Streamlit 1.64.0 and Plotly 6.9.0. See [license/pin review](phase11-license-review.md); platform metadata alone is not a complete legal clearance.

Byte scan of all 2,247 initial artifact files found the synthetic key marker only in the intentionally rejected input fixture (two preserved pytest paths) and the JUnit parameterized test name. It was absent from actual audit/session/evidence/database exports. No real keys were used. The 851-file recovery artifact scan also found no marker. Raw rejection-test fixtures are test data, not a publicly shareable audit bundle.

## Operator examples and remaining work

The existing [complete synthetic audit](../examples/phase9-static/index.html) and [illustrative partial examples](sample-reports/README.md) explain ready versus blocked/cancelled/synthesis-failed reports. Partial examples were generated offline from the report contract; no browser, model or cohort was run to create them. Actual pilot timeout measurements remain in the workflow evidence.

- [x] Release operations, install/startup/resources/cleanup/retention/recovery/troubleshooting documentation.
- [x] Workspace-aware explicit local resource setup; no automatic model download.
- [x] Pinned license/distribution review and downloadable development archives.
- [x] One full regression, retained failed evidence and targeted recovery repair acceptance.
- [x] Installed-wheel/browser/landing acceptance and offline report/screenshot/archive review.
- [x] Complete synthetic report and explicitly illustrative partial examples.
- [x] Resolve local planner latency/completion within the declared bounds; document any configuration/model change before validation.
- [x] Pass the two failed healthy journey selectors and the real three-profile defect/healthy pilot, then inspect comparison, export and protection evidence.
- [x] Rebuild final archives with reviewed gate records and examples; check off Phase 11 only after its remaining acceptance succeeds.

Live BYOK behavior, clean Windows/macOS archive acceptance, public GitHub/PyPI/release/site publication, arbitrary replicas, optional vision/Phoenix and human churn calibration remain outside this gate. Faster eligible BYOK inference is an operator option using an operator-owned free account/key, not a tested substitute for the failed local-model checks. Do not paste keys into chat or issues.

## Local planner follow-up checkpoints

- v1 [36903630720](https://github.com/TEE123754/Agentic/actions/runs/36903630720): 118 passed/4 failed; compact output alone did not resolve CPU prompt processing.
- v2 [36906806192](https://github.com/TEE123754/Agentic/actions/runs/36906806192): 48 passed/3 failed; enterprise delivery recovered, but agents repeatedly scrolled despite available controls.
- v3 [36908753768](https://github.com/TEE123754/Agentic/actions/runs/36908753768): 49 passed/3 failed; mobile defect abandonment was grounded, non-cognitive mobile reopened information, keyboard reached checkout but timed out.
- v4 [36911723397](https://github.com/TEE123754/Agentic/actions/runs/36911723397): **126 passed/1 failed in 1097.67 seconds**. All three healthy seeded journeys passed using actual pinned local inference. Mobile took 8 actions/166.38 inference seconds; keyboard took 23 actions/209.79 seconds; enterprise delivery took 1 action/32.05 seconds. These are observed samples, not latency guarantees. Zero sentinel requests and unchanged data. The only failure required ready status from an explicitly partial defect audit with excluded planner failures.

The corrected pilot requires valid blocker/abandonment evidence, accurate eligible counts and exclusion notices for a partial baseline; the healthy candidate still requires ready status, no missing evidence and 3/3 completions. No infrastructure fault becomes UX churn. [Remaining targeted pilot](https://github.com/TEE123754/Agentic/actions/runs/36914366167) is running. Current evidence union: 261 passing distinct cases out of 262; only the pilot remains. The three original unresolved-model items above are historical, superseded by this checkpoint. Final archive acceptance remains pending.

## Completed fixture release gate — October 2, 2026

The final v6 [focused window 36956658903](https://github.com/TEE123754/Agentic/actions/runs/36956658903), build `db5d34a`, passed **71/71 checks in 1319.509 seconds**, followed by installed-wheel CLI/browser/landing acceptance. The evidence union across the one full suite and subsequent affected-only windows is **265 distinct cases, all passing**; repeated cases are counted once. No model, timeout, patience budget or protection ceiling was increased. v5's two false failures came from focusing a filled textbox being classified as a dead-button click; v6 excludes filled-textbox local choices and exempts textbox/searchbox focus from that detector.

All three standalone healthy journey selectors pass. The real three-profile healthy checkout candidate is ready, **3/3 completed**, no missing evidence. The defect baseline is deliberately **partial**: one impatient-mobile evidence-grounded abandonment, one inconclusive enterprise agent failure and one keyboard timeout. Only one baseline session is eligible for UX analysis; the other two are excluded and remain limitations, not simulated churn. The saved comparison shows the observed Start checkout high-severity finding resolved and candidate raw completion count increased by three. It is not a human conversion effect or a statistically established rate. Both runs record zero sentinel requests and unchanged sentinel data.

Reviewed revision-2 aggregate reports, evidence references, recommendation, matched comparison, offline portable viewer screenshot, JSON/Markdown/HTML exports and the installed-package receipt. The inert Start checkout control has three valid evidence references and supports immediate visible feedback, a disabled state or a recoverable error. Viewer review made zero HTTP requests. Cleanup assertions passed. The portable viewer clearly preserves the partial baseline and excluded agent failures.

Archives from this immutable validation snapshot have 177 members each, contain bundled axe/license/configuration/site/viewer assets, and exclude models, environment files, credentials, evidence, runtimes, Git and virtual environments:

- Wheel: 932428 bytes; SHA256 `218390ca6d138896f281851e94a5f69ce9ef951b45212fcf3cff2da052802e1a`.
- Source: 954373 bytes; SHA256 `fbb186d8c26285f113611846dcf184db4458be3a01c260d78f2b05ed8d314996`.

The older unfinished checkboxes are superseded: local completion repair, real pilot/comparison/export review, archive installation/content review and the declared Phase 11 owned-fixture gate are complete. These snapshots precede this receipt and the requested new assessment/desktop phases; the new product workflow rebuilds its own candidate. Actual public publication, live BYOK model quality, arbitrary replicas and human calibration remain separate work. The defect pilot still demonstrates planner reliability limits; passing the declared partial-report gate is not a claim that every synthetic persona reliably diagnoses every defect.
