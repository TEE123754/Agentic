"""Streamlit command center for protected fixture cohorts and saved evidence."""

from __future__ import annotations

import os
from uuid import uuid4

import plotly.graph_objects as go
import streamlit as st

from frictionlab.dashboard.client import DashboardAPIError, DashboardClient


def _api():
    return DashboardClient(os.environ.get("FRICTIONLAB_API_BASE", "http://127.0.0.1:8765"))


def _call(operation, *args):
    try:
        with_client = _api()
        try:
            return operation(with_client, *args)
        finally:
            with_client.close()
    except (DashboardAPIError, ValueError) as exc:
        st.error(str(exc))
        return None


def _get(path):
    return _call(lambda client, value: client.get(value), path)


def _get_optional(path):
    return _call(lambda client, value: client.get_optional(value), path)


def _bytes(path):
    return _call(lambda client, value: client.bytes(value), path)


def _post(path, payload=None):
    return _call(lambda client, value, body: client.post(value, body), path, payload)


def _bar_chart(title, labels, values, color):
    figure = go.Figure(go.Bar(x=labels, y=values, marker_color=color))
    figure.update_layout(
        title=title,
        height=280,
        margin={"l": 20, "r": 20, "t": 45, "b": 25},
        yaxis_title="Synthetic sessions",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(figure, use_container_width=True)


def _setup(catalog):
    environment = catalog["environment"]
    st.subheader("New protected fixture run")
    st.caption(
        f"Only {environment['id']} ({environment['origin']}) · build {environment['build_id']}"
    )
    with st.expander("Protection and resource limits", expanded=False):
        st.write("Scope: bundled fixture · synthetic data · mocked integrations · no real orders")
        st.json(
            {
                "isolation": environment["isolation"],
                "blocked_operations": environment["prohibited_operations"],
                "limits": environment["limits"],
                "workers": catalog.get("workers", 0),
                "max_cohort_sessions": catalog["max_cohort_sessions"],
            }
        )
    profile_names = {item["id"]: item["name"] for item in catalog["profiles"]}
    journey_names = {item["id"]: item["description"] for item in catalog["journeys"]}
    with st.form("new_run"):
        personas = st.multiselect(
            "Synthetic profiles",
            list(profile_names),
            default=["impatient_mobile"],
            format_func=lambda value: profile_names[value],
        )
        journeys = st.multiselect(
            "Journeys",
            list(journey_names),
            default=["checkout_review"],
            format_func=lambda value: journey_names[value],
        )
        repetitions = st.number_input("Repetitions per profile/journey", 1, 5, 1)
        seed = st.number_input("Reproducible seed", 0, 2**32 - 1, 42)
        variant = st.selectbox(
            "Fixture behavior",
            [
                "healthy",
                "dead_button",
                "generic_validation",
                "delayed_feedback",
                "hidden_shipping",
                "focus_trap",
            ],
        )
        requested = len(personas) * len(journeys) * repetitions
        st.caption(
            f"{requested} session(s); maximum {catalog['max_cohort_sessions']}. "
            "Traffic, step, and runtime ceilings are fixed by the protected fixture policy."
        )
        allowed = bool(
            catalog["execution_enabled"]
            and personas
            and journeys
            and requested <= catalog["max_cohort_sessions"]
        )
        submitted = st.form_submit_button("Launch synthetic cohort", disabled=not allowed)
    if not catalog["execution_enabled"]:
        st.warning(
            "Start the local cohort API to enable runs. Review remains available only for saved API runs."
        )
    elif not allowed:
        st.info("Choose at least one profile and journey within the six-session cap.")
    if submitted and not allowed:
        st.error("Selected cohort exceeds the protected fixture limits.")
    elif submitted:
        payload = {
            "id": str(uuid4()),
            "environment": environment["id"],
            "personas": personas,
            "journeys": journeys,
            "repetitions": int(repetitions),
            "seed": int(seed),
            "artifact_directory": "artifacts/phase1",
        }
        result = _post(f"/runs?variant={variant}", payload)
        if result:
            st.session_state["run_id"] = payload["id"]
            st.rerun()


@st.fragment(run_every="3s")
def _live(run_id):
    progress = _get(f"/dashboard/runs/{run_id}/progress")
    if not progress:
        return
    left, right = st.columns(2)
    left.metric("Execution", progress["execution_status"])
    right.metric("Report", progress["report_status"])
    if progress["execution_status"] in {"queued", "running"} and st.button(
        "Cancel cohort", key=f"cancel-{run_id}"
    ):
        _post(f"/runs/{run_id}/cancel")
        st.rerun()
    for item in progress["sessions"]:
        with st.container(border=True):
            st.write(f"**{item['persona_id']} · {item['journey_id']}** — {item['status']}")
            cols = st.columns(4)
            cols[0].metric("Steps", item["step_count"])
            cols[1].metric(
                "Patience",
                item["patience_remaining"] if item["patience_remaining"] is not None else "—",
            )
            cols[2].metric(
                "Elapsed",
                f"{item['elapsed_seconds']}s" if item["elapsed_seconds"] is not None else "—",
            )
            cols[3].metric("Last action", item["last_action"] or "—")
            st.caption(
                f"Last result: {item['last_result'] or 'pending'} · Outcome: {item['outcome'] or 'pending'}"
            )
            if item["status"] in {"queued", "running"} and st.button(
                "Cancel session", key=f"cancel-{item['session_id']}"
            ):
                _post(f"/runs/{run_id}/sessions/{item['session_id']}/cancel")
                st.rerun()


def _overview(report):
    results = report["cohort_results"]
    st.write(report["executive_summary"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Requested", results["requested_sessions"])
    c2.metric("Executed", results["executed_sessions"])
    c3.metric("Eligible", results["eligible_sessions"])
    outcomes = results.get("outcome_counts", {})
    if outcomes:
        _bar_chart("Cohort outcomes", list(outcomes), list(outcomes.values()), "#405dd8")
    funnel = report.get("milestone_funnel", [])
    if funnel:
        _bar_chart(
            "Milestones passed (eligible sessions only)",
            [f"{item['journey_id']}: {item['milestone']}" for item in funnel],
            [item["passed_sessions"] for item in funnel],
            "#20a497",
        )
    st.subheader("Protection and review")
    protection = report["protection"]
    st.write(
        f"Boundary: {protection['boundary_scope']} · Sentinel requests: "
        f"{protection['sentinel_requests']} · Sentinel data unchanged: "
        f"{protection['sentinel_data_unchanged']}"
    )
    st.write(f"Review: {report['review']['status']}")
    for reason in report["review"].get("missing_evidence", []):
        st.warning(reason)
    for item in report.get("exclusions", []):
        st.warning(f"Excluded {item['kind']}: {item['reason']}")


def _trajectories(run_id, report):
    summaries = report.get("session_summaries", [])
    if not summaries:
        st.info("No browser session report was saved for this run.")
        return
    labels = {
        item[
            "session_id"
        ]: f"{item['persona_id']} · {item['journey_id']} · {item['session_id'][:8]}"
        for item in summaries
    }
    sid = st.selectbox("Session", list(labels), format_func=lambda value: labels[value])
    session = _get(f"/dashboard/runs/{run_id}/sessions/{sid}/report")
    if not session:
        st.info("Session evidence is unavailable; inspect report exclusions.")
        return
    st.caption(f"{session['execution_status']} · {session['terminal_reason']}")
    steps = session.get("trajectories", [])
    if not steps:
        st.info("This session has no saved browser trajectory.")
    for index, step in enumerate(steps):
        with st.expander(
            f"{index + 1}. {step['action']['kind'] if step.get('action') else 'none'} — {step['result']}"
        ):
            st.write(step["detail"])
            st.caption(
                f"Application {step['application_seconds']:.2f}s · Inference {step['inference_seconds']:.2f}s"
            )
            for position in ("observation_before", "observation_after"):
                obsid = step.get(position)
                if not obsid:
                    continue
                observation = _get(f"/dashboard/runs/{run_id}/sessions/{sid}/observations/{obsid}")
                if not observation:
                    continue
                st.write(f"**{position.replace('_', ' ').title()}** · {observation['route']}")
                st.caption(
                    f"Focus: {observation['focus']} · Validation: {observation['validation']}"
                )
                if observation["screenshot_available"]:
                    screenshot = _bytes(
                        f"/dashboard/runs/{run_id}/sessions/{sid}/screenshots/{obsid}"
                    )
                    if screenshot:
                        st.image(screenshot, caption="Saved masked screenshot")
    if session.get("patience_ledger"):
        st.subheader("Patience changes")
        st.dataframe(
            [
                {
                    "action": item["action_id"][:8],
                    "before": item["before"],
                    "after": item["after"],
                    "reason": item["reason"],
                }
                for item in session["patience_ledger"]
            ],
            hide_index=True,
        )


def _heatmaps(run_id, report):
    groups = report.get("heatmaps", [])
    if not groups:
        st.info("No compatible click heatmap is available for this run.")
        return
    labels = {
        item["id"]: f"{item['route']} · {item['input_mode']} · "
        f"{item['viewport']['width']}×{item['viewport']['height']} · "
        f"{item['pixel_width']}×{item['pixel_height']} px"
        for item in groups
    }
    selected = st.selectbox(
        "Compatible page and viewport", list(labels), format_func=lambda value: labels[value]
    )
    group = next(item for item in groups if item["id"] == selected)
    svg = _bytes(f"/dashboard/reports/{run_id}/heatmaps/{selected}")
    if svg:
        st.image(svg.decode("utf-8"), caption="Synthetic clicks on a saved masked screenshot")
    st.caption(
        f"{len(group['points'])} synthetic clicks; "
        f"{group['rage_click_clusters']} repeated-failure clusters. No human traffic is represented."
    )
    st.dataframe(
        [
            {
                "target": point["target_name"],
                "result": point["result"],
                "x": point["x"],
                "y": point["y"],
                "rage cluster": point["rage_cluster"],
            }
            for point in group["points"]
        ],
        hide_index=True,
    )


def _findings(run_id, report):
    findings = report.get("findings", [])
    if not findings:
        st.info(
            "No evidence-supported UX finding was published. Review exclusions and session outcomes."
        )
        return
    titles = {item["id"]: f"{item['severity'].upper()} · {item['title']}" for item in findings}
    selected = st.selectbox("Finding", list(titles), format_func=lambda value: titles[value])
    finding = next(item for item in findings if item["id"] == selected)
    st.write(f"**Observed:** {finding['observed_behavior']}")
    st.write(f"**Possible mechanism:** {finding['inferred_mechanism']}")
    st.write(
        f"**Affected:** {finding['affected_sessions']}/{finding['eligible_sessions']} "
        f"eligible synthetic sessions · Confidence {finding['confidence']:.2f}"
    )
    st.caption(finding.get("severity_rationale", ""))
    st.write(f"**Recommended change:** {finding['recommendation']}")
    st.write(f"**Verify:** {finding['verification']}")
    st.write("Profiles: " + ", ".join(finding.get("affected_profiles", [])))
    for ref in finding["evidence"]:
        if ref["path"].endswith(".png"):
            image = _bytes(f"/dashboard/reports/{run_id}/evidence/{ref['path'].split('/')[-1]}")
            if image:
                st.image(image, caption="Saved masked finding evidence")
        else:
            st.caption(f"Saved evidence: {ref['path']}")
    disposition = next(
        (item for item in report["review"]["dispositions"] if item["finding_id"] == selected), None
    )
    if disposition:
        st.caption(f"Current review: {disposition['status']} — {disposition['note']}")
    with st.form(f"review-{selected}"):
        status = st.selectbox(
            "Human disposition", ["confirmed", "dismissed", "requires_investigation"]
        )
        note = st.text_input("Review note", max_chars=2000)
        submitted = st.form_submit_button("Save reviewed revision")
    if submitted and not note.strip():
        st.warning("Add a short review note before saving.")
    elif submitted:
        updated = _post(
            f"/runs/{run_id}/findings/{selected}/review", {"status": status, "note": note}
        )
        if updated:
            st.rerun()


def _full_report(run_id, report):
    st.write(
        f"Revision {report['revision']} · {report['report_status']} · "
        f"review {report['review']['status']}"
    )
    downloads = (("json", "application/json"), ("md", "text/markdown"), ("html", "text/html"))
    for suffix, mime in downloads:
        content = _bytes(f"/reports/{run_id}/{suffix}")
        if content:
            st.download_button(
                f"Download {suffix.upper()}",
                content,
                file_name=f"frictionlab-{run_id}.{suffix}",
                mime=mime,
                key=f"download-{suffix}",
            )
            if suffix == "md":
                with st.expander("Read the full saved report"):
                    st.markdown(content.decode("utf-8"), unsafe_allow_html=False)


def main():
    st.set_page_config(page_title="FrictionLab · Local command center", layout="wide")
    st.title("FrictionLab")
    st.caption("Protected synthetic UX audits · local fixture only")
    catalog = _get("/dashboard/catalog")
    if not catalog:
        st.stop()
    with st.sidebar:
        st.write("**Connected local API**")
        st.caption(catalog["environment"]["origin"])
        st.caption(
            "The dashboard reads saved evidence through the API. It never opens the tested page."
        )
        st.button("Refresh saved state")
    _setup(catalog)
    runs = (_get("/dashboard/runs") or {}).get("runs", [])
    if not runs:
        st.info("No cohort runs yet. Launch a protected fixture run above to create an audit.")
        return
    options = {
        item["run_id"]: f"{item['run_id'][:8]} · {item['status']} · report {item['report_status']}"
        for item in runs
    }
    preferred = st.session_state.get("run_id")
    selection = st.selectbox(
        "Inspect run",
        list(options),
        index=list(options).index(preferred) if preferred in options else 0,
        format_func=lambda value: options[value],
    )
    st.session_state["run_id"] = selection
    st.subheader("Execution and report status")
    _live(selection)
    report = _get_optional(f"/reports/{selection}/json")
    if not report:
        st.info(
            "The audit is still being finalized. Refresh to inspect it when ready; failed exports retain an earlier partial report when available."
        )
        return
    tabs = st.tabs(["Overview", "Trajectories", "Heatmaps", "Findings", "Full report"])
    with tabs[0]:
        _overview(report)
    with tabs[1]:
        _trajectories(selection, report)
    with tabs[2]:
        _heatmaps(selection, report)
    with tabs[3]:
        _findings(selection, report)
    with tabs[4]:
        _full_report(selection, report)


if __name__ == "__main__":
    main()
