# Phase 10: open-source local product

The product is downloadable software, with browser, agent runtime, database, dashboard and evidence on the operator's machine. No FrictionLab account, hosted browser, billing proxy or automatic upload.

Remote inference will require the operator's own API key. Selected inputs go to that provider: remote inference cannot be fully offline. Local models remain an alternative without a key. Cloud transports passed mocked integration acceptance; live provider/account verification remains unperformed without supplied keys. See the [installation guide](phase10-installation.md).

## Construction checklist

- [x] Professional README with actual capabilities, quick start and limitations.
- [x] Clickable static product landing page and offline synthetic audit example.
- [x] MIT project license and contribution/security guidance.
- [x] Review third-party redistribution licenses before release.
- [x] Installable Python package, `frictionlab` console entry point, bundled config/viewer assets and downloadable source/wheel release.
- [x] `init`, `doctor`, portable startup/cleanup and resource-light defaults; no implicit large weight downloads or container installation.
- [x] BYOK Groq/Gemini transports with configurable currently eligible free model IDs; no bundled keys, proxy billing or paid fallback.
- [x] Read credentials only from environment/ignored local configuration; exclude secrets from prompts, logs, traces, DuckDB, reports and browser assets.
- [x] Integrate Phase 9 quota guard into every real request: hard request/token/runtime/retry ceilings, quota pause, configured available local fallback or visible pause.
- [x] Record actual provider/model identity and transitions; exclude mixed-provider strict comparisons. Model faults never count as UX abandonment.
- [x] Document selected provider input disclosure, no telemetry/upload defaults, and fully offline local inference.
- [x] Preserve owned-fixture restriction until arbitrary replicas prove network, data and integration isolation.
- [x] One clean-install end-of-phase acceptance on a disposable GitHub runner: CLI install/doctor, mocked BYOK success/429/timeout/budgets, secret exclusion, comparison identity, terminal fixture report and offline landing/sample navigation. At most one explicitly opted-in eligible free smoke request per configured provider. Without a key, record live integration as unverified.

Repository visibility, release publication and public hosting are separate release steps. The local landing page needs no publication. The initial remote gate passed 48/48 checks and installed-wheel CLI/browser acceptance. Installed landing/sample navigation then passed. The preflight reporting repair passed 2/2 affected cohort checks; 49 distinct pytest cases are verified overall. See the [validation record](phase10-validation.md). Browser/model runs are kept off the laptop. Public releases and live-provider quality are outside this mocked integration gate.

Documentation structure follows source-install, examples, model choice and contribution conventions in [browser-use](https://github.com/browser-use/browser-use) and [smolagents](https://github.com/huggingface/smolagents). Their hosted commercial offerings are not dependencies.

**Remaining beyond this gate:** own-key free-account/model verification; actual planner quality; clean Windows/macOS archive installation; public release/visibility and Phase 11 consolidated pilot validation. The checked implementation items do not imply any of those validations or publications occurred.
