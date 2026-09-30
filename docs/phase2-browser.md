# Phase 2 browser engine

Phase 2 builds the trusted browser broker used by later agents. It supports only a fresh copy of the bundled storefront. A deterministic demo is available; autonomous cohorts and external application URLs remain unavailable.

## Stack and source

| Component | Tool | Location |
|---|---|---|
| Browser control | Pinned Playwright Python / installed Chromium | `frictionlab/browser/broker.py` |
| Semantic grounding | Pinned browser-use DomService + cdp-use facade | `frictionlab/grounding/adapter.py` |
| Local fixture lifecycle | FastAPI, Uvicorn, owned loopback socket | `frictionlab/browser/runtime.py` |
| Request protection | Python fixed-upstream HTTP proxy, endpoint/payload policy | `frictionlab/protection/` |
| Evidence | Masked PNGs, sanitized DOM JSON, ARIA text, offline SVG marks | `frictionlab/browser/evidence.py`, `state.py` |
| Accessibility signals | axe-core 4.13.0, MPL-2.0, checksum-verified local bundle | `vendor/axe-core/`, `configs/axe-manifest.json` |
| Partial reports | Pydantic + local JSON/Markdown/HTML with embedded images | `frictionlab/reporting.py` |
| Acceptance | pytest, independent loopback sentinel, direct proxy probes, Ruff, Node syntax check | `tests/phase_02/` |

Primary API references: [Playwright network policy](https://playwright.dev/python/docs/network), [ARIA snapshots](https://playwright.dev/python/docs/aria-snapshots), and [axe-core repository](https://github.com/dequelabs/axe-core). Python versions remain locked in `uv.lock`. The axe distribution came through the free npm package registry from the named GitHub project; no npm process, network download, hosted scanner, or paid API is used during an audit.

## Run the deterministic demo

From the repository root:

```powershell
& '.venv\Scripts\python.exe' -m frictionlab browser-demo
```

Optional `--variant` values: `healthy`, `generic_validation`, `dead_button`, `delayed_feedback`, `hidden_shipping`, `focus_trap`. Optional `--persona`: `impatient_mobile`, `keyboard_low_vision`, `enterprise_evaluator`. This command runs fixed acceptance-style actions through the broker; it does not use a model or simulate cognitive patience. It creates its own ephemeral fixture services, so starting `serve` first is unnecessary.

The example run's fixture origin is a logical configuration reference. The broker binds a new numeric-loopback port and records its actual owned runtime origin in the report. It does not reinterpret that policy as authorization to launch an arbitrary existing localhost application. Profile/journey/policy configuration is saved with evidence.

`FRICTIONLAB_BROWSER_PATH` can point to a locally installed Chromium executable. This host uses installed Google Chrome; its actual version is recorded per run. A run never downloads a browser or model. If the executable is missing or startup fails, cleanup and partial reporting still run.

## Observe, act, and verify

Each observation receives a UUID and records browser target/document identity, DOM mutation epoch, state digest, visible viewport text, input-independent semantic signature, focus, validation, viewport coordinates, frame URLs, coverage gaps, and evidence references. browser-use supplies observed interactive candidates; Playwright owns execution. No browser-use action/navigation watchdog or planner is started.

Actions refer to the current observation and a current candidate. The broker rejects stale observations, replaced elements, changed input/viewport/scroll state, unknown targets, undeclared text, disallowed profile input, and fixture settings/reset operations. Candidate execution retains an element handle and checks its browser backend identity so an identical-looking replacement cannot inherit an old candidate ID.

Supported actions are click/tap, declared synthetic text input, approved keyboard keys, bounded vertical scrolling, bounded wait, and terminal capture. Keyboard profiles cannot click/tap; text insertion requires actual focus. Touch profiles use tap. Device viewport changes invalidate the old registry. Zoom uses Chromium page-scale emulation and is recorded; it is not a real operating-system magnifier or screen reader.

The broker waits for visible application feedback and tracked request completion within a bounded window. A click that merely focuses a dead button is not reported as progress. Application time includes action/feedback/evidence capture; no model time is folded into it. Completion is checked independently against the journey's heading/text/route criteria.

Screenshots mask form inputs. DOM exports remove scripts, frames, external-resource/action attributes, event handlers, and input values, and are saved as JSON rather than executable HTML. ARIA and visible text redact email addresses. Marks are composed in an offline SVG using an embedded PNG, without changing the tested page. Coordinate conversion records viewport offsets, CSS dimensions, and screenshot dimensions; a visual point must map to exactly one current candidate before it can ground an action.

Frame presence and extra pages are tracked, but frame, popup, shadow-root, and download actions are coverage gaps. Additional pages are closed; dialogs/downloads are dismissed/cancelled. Optional local axe inspection creates automated signals and refreshes the observation afterward. It does not establish compliance or simulate assistive technology.

## Website protection

The browser profile, fixture data, proxy, and sentinel are owned by the run. No real account, production credential, real payment, email, inventory mutation, or live website URL is eligible. The proxy relays only to a fixed numeric-loopback upstream. Allowed URLs, namespace, endpoint, method, JSON shape, payload size, and synthetic account references must all pass checks; a GET request to an order endpoint remains prohibited.

The gateway rejects other destinations, ambiguous/encoded routes, tunnels, protocol upgrades, foreign namespaces, unknown operations, live text, unsafe redirects, and oversized payloads. It does not follow redirects and does not relay credentials/cookies or a caller-selected Host header. Browser context routes enforce the same policy before requests, including popup requests; WebSockets are closed before upstream connection. Service workers are blocked at context creation. Unknown destinations fail closed.

Mandatory startup probes exercise an independent proxy denial, forbidden operation disguised as GET, redirect, image, iframe, fetch, beacon, WebSocket, and service-worker attempt. The separate local sentinel must receive zero requests and retain its seeded balance. These probes are setup checks and never enter persona patience calculations.

The proxy applies a sliding one-second request ceiling and upstream concurrency limit. The broker applies a step ceiling, runtime watchdog, and emergency cancellation. Cleanup closes CDP/context/Playwright and local services, resets only the owned namespace after pending server requests finish, and removes the verified project-owned temporary profile. It then writes a report using saved evidence only.

**Scope limit:** These are validated controls for the owned fixture and supported browser transports, not an OS/container network sandbox. Docker/Podman are absent. External replicas and generated Python remain disabled. WebRTC/alternate clients/unsupported browser features and malicious arbitrary applications must not be considered isolated by this proxy. Phase 3 still requires the stronger code-worker boundary before any generated code executes.

## Reports and acceptance

Each broker lifecycle writes `artifacts/phase2/runs/<UUID>/report.json`, `report.md`, `report.html`, and `evidence/`. Saved images are embedded in offline HTML. Network blocks, traffic totals, startup checks, upstream arrival evidence, cleanup results, action arguments/results, independent completion, and missing UX coverage are available. Reports remain `partial` because autonomous UX analysis, calibrated findings, heatmaps, and cognitive diagnoses belong to later phases.

The Phase 2 suite ran once after construction, followed by targeted repairs only. Relevant Phase 1 regressions were included because shared modules changed. All 83 distinct checks pass. No Phase 0 model/browser scenario was repeated. [Validation review](phase2-validation.md) records commands, original/repair evidence, and known limitations.

The normal API `/runs` remains blocked: it represents an autonomous cohort, which Phase 2 does not implement. Later phases can consume `BrowserBroker` through trusted typed tools rather than exposing unrestricted Playwright objects to generated code.
