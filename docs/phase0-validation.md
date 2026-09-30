# Phase 0 acceptance and evidence review

**Run:** `20260929T091343.937322Z`  
**Result:** PASS — 16 of 16 acceptance checks, zero missing checks.  
**Environment:** Local bundled fixture only. No deployed website or real user data used.  
**Validation count:** One complete browser/model scenario. No rerun required.

## What was demonstrated

1. A fixed-upstream loopback proxy rejected an independent request to a disallowed sentinel before contacting it.
2. Playwright launched headless Chrome 153.0.8010.53 using a new project-owned profile.
3. Fixture probes attempted fetch, frame navigation, image load, beacon, service-worker registration, and WebSocket traffic outside the declared fixture boundary. Transport policies blocked the disallowed traffic, and service-worker registrations stayed at zero.
4. The browser-use DOM service attached to the exact Playwright target without a BrowserSession, event bus, navigation watchdog, or action watchdog.
5. The adapter extracted two visible buttons and supplied them to local Qwen3-4B Q4_K_M through llama.cpp b11247.
6. The model chose observed candidate 3, Start checkout, with a valid observation ID. Playwright executed the generated locator; no authored journey selector or generated Python action code was used.
7. Independent heading verification found Order review. The UI explicitly stated that no order had been placed.
8. The action registry invalidated after execution. The disallowed-service sentinel still had zero requests.
9. Browser, CDP connection, model process, proxy, fixture, and sentinel shut down without reported cleanup errors.
10. JSON, Markdown, and self-contained HTML reports were produced from recorded evidence, without reopening the fixture.

## Measurements

| Metric | Result |
|---|---|
| Model load/startup | 4.187 s |
| Model request | 8.546 s |
| Prompt/output tokens | 199 / 101 |
| Browser action and outcome wait | 0.047 s |
| Full scenario | 16.844 s |
| Peak combined monitored process RSS | 5.311 GiB |
| Budget | 8 GiB |

Combined RSS sums the runner and its child processes; shared mapped pages can be counted more than once. This is a conservative process-memory measurement, not a complete system RAM benchmark. The one small prompt does not predict complex journey latency or concurrent cohort performance.

## Evidence reviewed

- [Observed state and candidate registry](../artifacts/phase0/20260929T091343.937322Z/observation.json).
- [Before ARIA state](../artifacts/phase0/20260929T091343.937322Z/before.aria.txt).
- [After ARIA state](../artifacts/phase0/20260929T091343.937322Z/after.aria.txt).
- [Final screenshot](../artifacts/phase0/20260929T091343.937322Z/after.png): Order review and the $70 total were visibly present.
- [Structured report](../artifacts/phase0/20260929T091343.937322Z/report.json): all checks true, sentinel events empty, no cleanup errors.
- [Detailed readable report](../artifacts/phase0/20260929T091343.937322Z/report.md).
- [Offline HTML report](../artifacts/phase0/20260929T091343.937322Z/report.html): assets and screenshots are inline, with no remote scripts.

The proxy also rejected Chrome background requests to undeclared destinations. Those attempts were rejected locally; they are not reported as UX friction.

## Limits carried forward

- No real-world website, cognitive persona, multi-agent cohort, abandonment detector, accessibility usability claim, or churn prediction was evaluated.
- Podman/Docker is not installed. The proxy and browser policy are a controlled fixture boundary, not OS-enforced isolation against arbitrary code or unsupported browser transport. That boundary must be implemented and validated in later phases before accepting external targets.
- The Phase 0 model endpoint is ephemeral and loopback-only, and stops after the scenario. It has no authentication configured. The persistent model/tool broker in Phase 3 must define local authentication and browser-origin restrictions before serving less-trusted content.
- Installed Chrome was used because the dedicated Playwright download timed out. Exact browser version is recorded, but the executable can update separately from the lockfile.
- Optional SmolVLM is configured but disabled and unvalidated. No vision localization quality claim is made.

## Required remaining Phase 0 work

None for the documented fixture-only feasibility gate. Phase 1 can begin. Strict deployment isolation and generated-code execution remain blocked until their later implementation gates pass.
