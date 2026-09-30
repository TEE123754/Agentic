# Architecture and isolation decisions

## Browser ownership

Playwright launches one fresh persistent browser context in a project-owned temporary profile, installs routes and WebSocket policy, executes validated actions, captures evidence, and owns teardown. The CDP endpoint binds only to loopback.

Use the pinned browser-use `DomService` directly with a small session facade around `cdp-use`. The facade attaches only to the exact Playwright page target. Do not call `BrowserSession.start()`, `BrowserSession.connect()`, `Agent.run()`, or `attach_all_watchdogs()`.

This avoids browser-use's navigation, action, popup, permission, download, proxy-auth, and lifecycle watchdogs. Its DOM service supplies interactive candidates and accessibility-derived text; Playwright remains the sole action executor. This is a version-sensitive adapter, so `uv.lock` pins its complete dependency graph. Cross-origin frames and shadow-root action mapping are explicitly outside this single-page spike.

Candidates are bound to a fresh observation UUID, current DOM digest, generated XPath, accessible name, and browser target ID. Actions use only the current registry and reject stale state. XPaths are generated from observed DOM nodes rather than authored journey scripts. The model returns a constrained action object; no generated Python is executed in Phase 0.

## Fixture-only protection

The Phase 0 scenario has no user-supplied URL. It serves a bundled storefront on an ephemeral loopback port and starts a second local sentinel representing a disallowed live service. All dependencies are inline/local. No real deployed website is contacted.

The browser uses a local explicit HTTP proxy with Chromium's implicit loopback proxy bypass disabled. The proxy can relay GET requests only to the exact loopback fixture origin and known fixture paths. It rejects CONNECT tunnels, other origins, credentials in URLs, unknown paths, and mutating methods. Its upstream destination is fixed; it never resolves or relays an arbitrary caller-provided hostname.

Playwright adds a second pre-request allowlist, blocks service workers and disallowed WebSocket connections, and logs rejected browser requests. Page navigations, fetches, images, and beacons to the sentinel are intentional fixture probes, not real network targets. A direct proxy probe verifies the deny rule independently of Playwright interception. Negative probes stop before the local model decision, and do not enter persona patience calculations.

Disable browser-use anonymized telemetry and cloud sync before imports. Inference HTTP clients disable environment proxy inheritance and use a fixed loopback endpoint. The model server binds to 127.0.0.1, uses CPU inference, and does not receive credentials. Setup downloads are a separate explicit command and are never run during an audit.

## Strict deployment prerequisite and honest limitation

An HTTP proxy and browser policy are not an OS-enforced sandbox. They do not prevent an arbitrary generated Python process, extension, alternate socket client, or future unsupported browser feature from bypassing configuration. The Phase 0 fixture demonstrates known transport controls and shared-target interoperability, not unrestricted production-grade isolation.

Podman/Docker is absent on the current host. Before enabling arbitrary user URLs or generated-code agents, require an isolated container/VM with no live-service routes, a disposable data copy, mocked integrations, and a fixed controlled-egress gateway. Execution must fail closed when that prerequisite is absent. Phase 2 must validate the network boundary; Phase 3 must validate generated-code isolation. Do not describe the current spike as safe to run against production.

## Generated-code design for Phase 3

- smolagents code runs as an unprivileged worker in a disposable Podman container, with no host mounts except a bounded scratch directory, no credential environment, no socket mounts, no container control socket, and no general network.
- The worker can call only a local trusted tool broker through a deliberately constrained IPC channel. The broker validates observation IDs, tool arguments, destinations, data references, quotas, and operation permissions.
- Browser/model processes live outside the generated-code worker. Their secrets are never returned to the worker. Browser network access is limited to the isolated replica and mock services through the controlled gateway.
- Bound CPU, RAM, runtime, process count, output size, and tool-call count. Kill the worker on timeout and retain evidence.
- An import allowlist is supplementary, not the execution boundary. Until the container boundary passes its phase gate, generated-code execution remains disabled.

## Model and dependency provenance

`configs/resource-manifest.json` records the exact llama.cpp release asset, model repository revision, URLs, declared licenses, and expected/observed SHA-256 hashes. `uv.lock` records Python dependencies and artifact hashes. The runtime downloader validates checksums and archive paths before extraction.

The latest named stable llama.cpp release did not provide the requested Windows CPU asset. Select and pin the most recent official build release that does, rather than silently replacing it with a third-party binary.

Core licenses: Playwright Apache-2.0; browser-use MIT; cdp-use MIT; llama.cpp MIT; Qwen3 weights Apache-2.0; Pydantic MIT; httpx BSD-3-Clause; psutil BSD-3-Clause. Export installed metadata to `docs/dependency-manifest.json` and retain the locked versions. Provider SDKs may arrive as browser-use transitive dependencies; installation does not mean those providers are called.

## Reporting and validation

After the spike stops, flush evidence, validate acceptance checks, and generate local JSON, Markdown, and self-contained HTML reports. Report generation uses stored results and never reopens the fixture. Both successful and failed scenarios receive a report; absent evidence is marked missing. The report explicitly excludes multi-agent behavior, cognitive calibration, UX audits, vision quality, and kernel-level isolation until their later phases.

Run the bundled Phase 0 scenario once after construction. If a check fails, repair the defect and rerun only the affected integration flow. Record each attempt separately; do not overwrite an unfavorable result.

## Phase 1 foundation

Use one flat, importable Python package rather than separate local packages until the application has independent services. FastAPI exposes the bundled fixture and configuration/report endpoints; `python -m frictionlab` provides serve and offline validate. No browser/model module is imported by application startup. Environment configuration accepts only the fixture's explicit loopback origin and complete synthetic-data/mock declarations. These declarations are prerequisites, not transport evidence; `/runs` stays blocked until Phase 2.

Use UUID-scoped in-memory fixture state for development. Reset preserves the defect variant, clears only the owned namespace, and reproduces account generation deterministically. Mock effects are local event records. The sentinel API records a rejected mock attempt; the independent Phase 0 sentinel is still required for later actual network protection checks.

Export strict Pydantic contracts as JSON Schema. Keep candidate IDs bound to observation/target identity, type actions through synthetic data references, and require evidence/denominators/review consistency in reports. Generate deterministic partial exports for blocked and pre-navigation failure outcomes without invoking models or reconnecting to a target. Persistence and finalization recovery remain later phases.

Phase 1 acceptance uses in-process HTTP requests and forbids application sockets/DNS. On Windows, the trusted standard-library socketpair call alone may create its event-loop self-pipe; this exception is scoped to that call and thread. Preserve initial and repair evidence separately and merge latest results without rerunning passing checks.

## Phase 2 trusted browser boundary

The broker creates the bundled replica itself on a fresh loopback socket. The configured fixture origin is a logical reference; execution does not grant access to an arbitrary service listening at that port. Runtime origin, resolved configuration, browser version, device settings, and fixture content hash are recorded. The user-supplied configuration remains subject to the Phase 1 offline restrictions.

Browser context routes and the fixed-upstream proxy share endpoint/payload rules. Only known fixture paths, owned namespace creation/accounts/checkout, and declared synthetic text are accepted. The proxy never resolves a caller-selected hostname or follows a redirect, rejects tunnels/upgrades/foreign operations, and applies sliding request/concurrency limits. Independent local-sentinel probes are mandatory before actions. They are excluded from persona UX evidence and do not establish kernel isolation.

Use retained element handles with browser backend identity, observation UUID, document UUID, DOM mutation epoch, and input/viewport/scroll digest. A visually identical replacement is a different element and requires a new observation. Export masked screenshots without caret hiding or animation alteration: acceptance found that caret hiding could leave an empty input style attribute. Draw candidate marks in offline SVGs rather than changing the application's DOM.

Save sanitized DOM as JSON, redact ARIA/text, and embed PNGs in offline reports. Preserve action arguments/results, focus/validation, network policy events, independent upstream arrivals, terminal reasons, and cleanup. Local axe-core is verified against its manifest and does not fetch runtime assets. These signals are raw evidence until later UX detection/review phases.

Step/runtime/cancellation limits stop execution; cleanup closes owned services before resetting data to avoid in-flight state reappearing. Reporting reads saved evidence after teardown, remains partial for unimplemented UX analysis, and never launches another browser run. All attempts, including failures, retain separate reports. The Phase 2 gate passed 83 distinct checks; the unsupported OS/container boundary continues to block external replicas and generated code.

## Phase 3 bounded autonomous planning

The current Windows host lacks Podman/Docker and usable WSL. Use smolagents 1.26.0 `ToolCallingAgent` with reviewed Python tools rather than evaluating generated code. The framework provides orchestration; Pydantic, fresh observation schemas, and the trusted broker enforce permissions independently of prompts. This follows the project's [security guidance](https://github.com/huggingface/smolagents), which distinguishes a local interpreter from an OS sandbox. The full generated-code worker remains an unmet gate, and isolated-code mode exports a blocked report before browser/model startup.

The owned hash-verified llama.cpp/Qwen process is local, sequentially shareable, and outside browser state. A minimal launch environment excludes provider credentials, proxies, and native tool overrides. Disable native agent, UI, and MCP proxy functions. Cap native prompt cache at 512 MiB: the documented [8,192 MiB default](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md) caused growth above the sampled 8 GiB process budget during acceptance. The watchdog is a sampled RSS ceiling, not kernel-enforced isolation. Its termination, request timeouts, malformed decisions, and grounding failures remain infrastructure/agent outcomes.

Use `/apply-template` and `/tokenize` to count the actual formatted prompt before inference. Default planning bounds are 2,800 input tokens, 256 output tokens, 24 decisions/tool calls, 240 seconds, 60 seconds/request, and no provider retry. Every response is constrained to the current action schema and assigned a trusted UUID. Reject raw text credentials, stale IDs, extra tools, multi-tool decisions, and finish before independently verified milestones. Verify after every action and end immediately on success rather than requiring a further model decision.

Each session gets separate bounded memory. Touch/mouse perception contains viewport-visible controls and text; keyboard perception adds accessible content and actual focus. Historical keyboard notes retain paragraph facts without stale controls/dialog markup. Remember successful keyboard transitions while preserving retries for ineffective actions. Grounded focus governs activation/typing, and Escape requires a current dialog. These rules support planning and do not assert human cognition or real assistive-technology fidelity.

Log decisions, rationale, token counts, inference time, actual actions, independent completion, and stop/cleanup state. Model latency stays separate from application response time. Export detailed offline partial reports for all terminal outcomes, including rejected configuration before execution. Report review uses saved evidence and never reruns the website. Preserve original unfavorable reports; aggregate later results without rewriting history. The typed-tools fixture scope passed 100 distinct checks after targeted repairs, while its initial 0/3 healthy threshold remains failed and the full generated-code/container phase remains partial.
