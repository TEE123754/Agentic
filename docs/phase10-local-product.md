# Phase 10: open-source local product

The product is downloadable software, with browser, agent runtime, database, dashboard and evidence on the operator's machine. No FrictionLab account, hosted browser, billing proxy or automatic upload.

Remote inference will require the operator's own API key. Selected inputs go to that provider: remote inference cannot be fully offline. Local models remain an alternative without a key. Current cloud transports are **not implemented**.

## Construction checklist

- [x] Professional README with actual capabilities, quick start and limitations.
- [x] Clickable static product landing page and offline synthetic audit example.
- [x] MIT project license and contribution/security guidance.
- [ ] Review third-party redistribution licenses before release.
- [ ] Installable Python package, `frictionlab` console entry point, bundled config/viewer assets and downloadable source/wheel release.
- [ ] `init`, `doctor`, portable startup/cleanup and resource-light defaults; no implicit large weight downloads or container installation.
- [ ] BYOK Groq/Gemini transports with configurable currently eligible free model IDs; no bundled keys, proxy billing or paid fallback.
- [ ] Read credentials only from environment/ignored local configuration; exclude secrets from prompts, logs, traces, DuckDB, reports and browser assets.
- [ ] Integrate Phase 9 quota guard into every real request: hard request/token/runtime/retry ceilings, quota pause, configured available local fallback or visible pause.
- [ ] Record actual provider/model identity and transitions; exclude mixed-provider strict comparisons. Model faults never count as UX abandonment.
- [ ] Document selected provider input disclosure, no telemetry/upload defaults, and fully offline local inference.
- [ ] Preserve owned-fixture restriction until arbitrary replicas prove network, data and integration isolation.
- [ ] One clean-install end-of-phase acceptance on a disposable GitHub runner: CLI install/doctor, mocked BYOK success/429/timeout/budgets, secret exclusion, comparison identity, terminal fixture report and offline landing/sample navigation. At most one explicitly opted-in eligible free smoke request per configured provider. Without a key, record live integration as unverified.

Repository visibility, release publication and public hosting are separate release steps. The local landing page needs no publication. No packaging or BYOK phase gate has passed yet.

Documentation structure follows source-install, examples, model choice and contribution conventions in [browser-use](https://github.com/browser-use/browser-use) and [smolagents](https://github.com/huggingface/smolagents). Their hosted commercial offerings are not dependencies.
