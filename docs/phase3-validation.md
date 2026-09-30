# Phase 3 acceptance record

**Recorded:** September 30, 2026, Asia/Kuala_Lumpur. Raw artifacts use UTC timestamps.

**Result:** The typed-tools fixture implementation is verified after targeted repairs. All **100 distinct checks pass**, with no unresolved checks. Each supported profile has an independently verified healthy journey. The original first-pass healthy threshold failed **0/3** and is retained. **Full Phase 3 remains partial:** the generated-code/container worker is unimplemented and disabled.

## Scope and environment

Acceptance used only the bundled disposable storefront, synthetic accounts, local mocks, fixed-upstream proxy, and independent local disallowed-service sentinel. No external website or staging/production deployment was contacted. Playwright 1.63.0 and browser-use 0.13.10 operated on the same page target; installed Chrome 154.0.8037.58 ran in owned temporary profiles. smolagents 1.26.0 used reviewed typed tools through the authoritative broker. Healthy journeys used actual local Qwen3-4B Q4_K_M decisions, seed 42, checksum-verified llama.cpp b11247, CPU inference, and no cloud keys. Deterministic model substitutes were used only for negative controls.

The 100 distinct checks comprise 48 Phase 3 checks, 15 report/CLI regressions, 17 contract regressions, and 20 protection-policy regressions. They cover model format/argument validation, input/output context budgets, current candidate IDs, perceived/focused controls, premature completion, unknown/multiple tools, prompt bypasses, provider/runtime/step/tool/retry limits, cancellation, resource failure, credential-free environment, memory termination attribution, keyboard memory, preflight exports, generated-code rejection, offline reports, and owned-resource cleanup.

## Execution policy and retained history

Implementation and its acceptance harness were completed before testing. One consolidated initial batch ran; subsequent batches selected affected failures/new safeguards only. Passing enterprise and mobile browser/model journeys were not rerun. Mobile's privacy assertion repair reviewed its successful stored run offline, without model/browser execution. The last three preflight checks also ran offline. Changed Python files passed Ruff after targeted style fixes. No Phase 0 run or complete regression suite was repeated.

| Retained batch | Selected checks | Failures | Interpretation |
|---|---:|---:|---|
| `validation-initial.xml` | 88 | 3 | Healthy first-pass threshold failed; negative controls and relevant regressions passed |
| `validation-repair-1.xml` | 8 | 2 | Enterprise completed; mobile scroll feedback and keyboard focus defects remained |
| `validation-repair-2.xml` | 4 | 2 | Mobile independently completed; its privacy assertion was overly broad. Keyboard model hit sampled memory limit |
| `validation-repair-3-offline.xml` | 1 | 0 | Corrected mobile assertion reviewed saved successful evidence only |
| `validation-repair-4-keyboard.xml` | 4 | 1 | New runtime/environment/memory guards passed; keyboard historical control markup caused repeated Escape |
| `validation-repair-5-keyboard.xml` | 2 | 0 | Keyboard independently completed; current-dialog/history safeguard passed |
| `validation-repair-6-preflight.xml` | 3 | 0 | Invalid configuration, disabled selection, and invalid agent settings exported blocked reports without execution |

Selected check counts overlap. The [merged XML](../artifacts/phase3/validation.xml) keeps the latest result for each distinct check; the [structured record](../artifacts/phase3/validation.json) retains all batch counts, original threshold failure, and every real model outcome. Merging saved records launches no browser or model.

## Independently verified healthy journeys

| Profile | Goal | Model decisions | Inference time | Application time | Saved report |
|---|---|---:|---:|---:|---|
| Enterprise evaluator | Delivery information | 1 | 11.125 s | 0.485 s | [Offline report](../artifacts/phase3/runs/8271c88e-eaeb-4ee2-94a0-ef92a15fa963/report.html) |
| Impatient mobile | Checkout review | 16 | 232.030 s | 5.221 s | [Offline report](../artifacts/phase3/runs/204a3c49-dca9-4e48-a473-aeaf25fb46a2/report.html) |
| Keyboard low vision | Keyboard checkout | 11 | 153.096 s | 2.595 s | [Offline report](../artifacts/phase3/runs/f192ad61-4aba-456b-b1e7-aab860d3b423/report.html) |

The keyboard profile used keyboard actions only at 200% page scale and completed independent assertions. This does not establish real screen-reader or elderly-user behavior. Its successful runtime sampled 5,544,013,824 bytes peak model RSS (5.163 GiB), below the 8 GiB ceiling, with the 512 MiB native prompt-cache setting. Earlier successful mobile/enterprise reports precede that cache repair and are preserved without rewriting their configuration evidence.

**Rate interpretation:** There were ten real healthy attempts across successive implementation versions, with three completions. Latest per-profile coverage is 3/3 after documented repairs; initial coverage was 0/3. Neither number is a calibrated population completion rate. Mobile's 232-second inference time approaches the 240-second planning ceiling; application timing is separate. Total lifecycle duration additionally includes startup, observation/capture, reporting, and cleanup overhead.

## Repairs and failure attribution

- Premature finish is excluded until completion criteria are true. The trusted verifier checks each action and ends the agent immediately on actual success.
- Bounded memory retains previously perceived paragraph facts and observed control names. Keyboard history excludes stale dialog/control markup and distinguishes current focus from prior notes; Escape requires a current accessible dialog.
- Scroll records real viewport movement as progress; schema increments are bounded. Keyboard activation requires a grounded allowed focus, and typing requires an applicable textbox and declared synthetic reference.
- The native default prompt cache could grow alongside the loaded weights and exceed the sampled 8 GiB process budget. The owned process now caps its cache at 512 MiB, strips credential/runtime-tool environment variables, and disables native agent/UI/MCP facilities. Memory termination is classified as infrastructure failure.
- Earlier run `73075c5a-a937-4f01-b0ea-f40d16fe6b87` retains its original `ReadError` diagnosis. Its sampled peak was 8,652,943,360 bytes, and the watchdog stopped the model; review attributes this to model memory termination rather than website UX. That original immutable report was not rewritten to hide the failure.
- The privacy harness previously rejected the public `@fixture.invalid` domain hint; it now rejects full addresses. The successful mobile browser/model run was reviewed offline.
- CLI configuration/selection/settings failures now export a factual blocked Phase 3 report before any browser/model starts and without echoing rejected sensitive values.

## Protection, cleanup, and report review

All **19 terminal outcomes** have JSON, Markdown, and self-contained offline HTML reports. These contain 84 bounded model decision records across real healthy attempts, including failures, plus action/application/model timings, stop reasons, independent checks, protection logs, masked observations, scope, and limitations. Three preflight cases started no browser/model/sentinel and made zero target requests. The other 16 retained reports show zero sentinel requests and unchanged sentinel state; the aggregation distinguishes unstarted sentinels from tested zero-traffic controls.

Accepted sessions cleaned up their owned Chrome profiles, CDP connections, fixture/proxy/sentinel services, and synthetic data. The shared local model intentionally remained alive when individual reports were exported; its owning test fixture stopped it after the selected batch and verified teardown. Therefore `model_process_stopped: false` in a session's export describes shared ownership at that moment, not a leaked model process. The stop/drain and cleanup checks passed.

Evidence references and exported sections were reviewed from saved files: all 19 reports validated against the report contract, all 57 export files exist, every visual evidence reference resolves, every HTML report contains the planner-decision section, and no HTML contains scripts. This review launched no browser/model. The terminal mobile screenshot was visually inspected: it shows Order review, $70 including shipping, and “No order has been placed.” Reports contain no remote scripts and do not reconnect to the fixture. Zero generated Python, external websites, or vision calls were recorded. Findings/abandonment lists remain empty because cognition and evidence-based UX detection are unbuilt; infrastructure failures are not presented as user churn.

## Remaining gate and limitations

No required task remains in the verified typed-tools fixture scope. Full Phase 3 requires a free OS/container runtime and an unprivileged generated-code worker with no general egress, no host credentials/control sockets, constrained IPC/scratch, resource ceilings, and explicit escape/timeout/cleanup checks. Podman/Docker and usable WSL are absent. Code execution and external replicas stay disabled until those boundaries pass.

Optional vision, pinned dedicated Chromium, broader page/frame behavior, real assistive technology, human calibration, and repeated-seed quality evaluation remain unvalidated. Phase 4 friction/patience, Phase 5 cohorts/persistence, and later full UX reports, recommendations, heatmaps, dashboard, and calibration have not started. The current detailed reports explicitly remain partial for those missing capabilities.
