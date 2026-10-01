# FrictionLab run report

Run: `ff26ae15-bf92-4471-a7bd-937e5c17d74c`

Execution: **blocked**; report: **partial**

Reason: Illustrative configuration rejection: arbitrary external targets are unsupported.

## Executive summary

Illustrative partial-report example. No website, model or user cohort was run to produce this example. No UX conclusions are supported.

## Scope and reproducibility

```json
{
  "phase": 1,
  "build_id": null,
  "environment_id": null,
  "personas": [],
  "journeys": [],
  "seed": null,
  "configuration_hash": null,
  "runtime_metadata": {
    "illustrative_example": true
  }
}
```

## Website protection

```json
{
  "target_requests": 0,
  "environment_validated": false,
  "network_boundary_validated": false,
  "events": [
    {
      "id": "1ca18cd3-c27f-4a1d-a7c5-faeb2ef50ab4",
      "decision": "blocked",
      "layer": "configuration",
      "reason": "Illustrative configuration rejection: arbitrary external targets are unsupported.",
      "occurred_at": "2026-10-01T17:45:29.362115Z"
    }
  ],
  "cleanup_outcome": "No browser, model process, or external resources were started.",
  "boundary_scope": "unvalidated",
  "traffic_metrics": {},
  "sentinel_requests": null,
  "sentinel_data_unchanged": null
}
```

## Cohort results

```json
{
  "requested_sessions": 0,
  "executed_sessions": 0,
  "eligible_sessions": 0,
  "outcome_counts": {}
}
```

## Individual trajectories

Unavailable: no browser trajectory was recorded.

## UX findings

None asserted; no observed UX evidence.

## Visual evidence and heatmaps

Unavailable: no screenshots or interactions were captured.

## Abandonment explanations

No synthetic abandonment diagnosis was asserted.

## Recommendations

```json
[
  "Resolve the documented configuration issue or finish the browser execution phase before running a cohort.",
  "Require validated replica/network and generated-code isolation before enabling external application targets."
]
```

## Comparison

No baseline/candidate comparison exists because execution did not start.

## Review and limitations

```json
{
  "status": "configuration_reviewed",
  "method": "Documentation example generated locally from the partial-report contract; not an execution measurement.",
  "missing_evidence": [
    "Browser trajectories",
    "Screenshots",
    "Observed UX events",
    "Outcome measurements"
  ],
  "limitations": [
    "This report contains configuration review only; autonomous cohort execution is unavailable.",
    "No UX issue, human abandonment cause, or network sandbox guarantee can be inferred from this report."
  ],
  "dispositions": []
}
```
