from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from controlplane.eval.report import build_report
from controlplane.ledger import LedgerStore
from controlplane.models import HarmVector, Interaction
from controlplane.service import AssessmentEngine
from controlplane.sim.scenarios import run_scenarios
from controlplane.sim.traffic import ensure_corpus

ROOT = Path(__file__).resolve().parents[1]

st.set_page_config(
    page_title="ControlPlane assurance console",
    page_icon=":material/shield:",
    layout="wide",
)


@st.cache_data(show_spinner="Running the seeded evaluation...")
def load_artifacts() -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    interactions = ensure_corpus(ROOT / "data")
    evaluation_path = ROOT / "reports" / "evaluation.json"
    scenario_path = ROOT / "reports" / "scenarios.json"
    if evaluation_path.exists():
        frame = pd.read_csv(ROOT / "reports" / "evaluation.csv")
        detail = json.loads(evaluation_path.read_text(encoding="utf-8"))
    else:
        frame, detail = build_report(ROOT, interactions)
    evaluation_engine = AssessmentEngine(ROOT)
    evaluation_engine.calibrate(
        [interaction for interaction in interactions if interaction.split == "calibration"]
    )
    if scenario_path.exists():
        scenarios = json.loads(scenario_path.read_text(encoding="utf-8"))
    else:
        scenarios = run_scenarios(ROOT, evaluation_engine, interactions, frame)
    return frame, detail, scenarios


@st.cache_data(show_spinner=False)
def load_attention() -> dict[str, Any] | None:
    """The reviewer-queue comparison, when `make attention` has been run."""
    path = ROOT / "docs" / "results" / "attention.json"
    if not path.exists():
        return None
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def load_relearn() -> dict[str, Any] | None:
    """What the last calibration refit found, when `make relearn` has been run."""
    path = ROOT / "docs" / "results" / "relearn.json"
    if not path.exists():
        return None
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


@st.cache_resource
def assessment_engine() -> AssessmentEngine:
    interactions = ensure_corpus(ROOT / "data")
    runtime = AssessmentEngine(ROOT, ledger_path=ROOT / "data" / "audit.db")
    runtime.calibrate(
        [interaction for interaction in interactions if interaction.split == "calibration"]
    )
    return runtime


def rupees(value: float) -> str:
    return f"₹{value:,.0f}"


VERDICT_COLOURS = {
    "allow": "green",
    "annotate": "blue",
    "hold": "orange",
    "abstain": "gray",
    "block": "red",
}


def render_harm(risk: dict[str, float]) -> None:
    harm = pd.DataFrame(
        sorted(risk.items(), key=lambda item: -item[1]),
        columns=["Harm axis", "Probability"],
    )
    st.dataframe(
        harm,
        hide_index=True,
        column_config={
            "Probability": st.column_config.ProgressColumn(
                format="%.3f", min_value=0.0, max_value=1.0
            )
        },
    )


def render_decision(data: dict[str, Any]) -> None:
    """The shared view for any scenario that is one decision on one interaction."""
    verdict = str(data.get("verdict", "—"))
    st.badge(verdict, color=VERDICT_COLOURS.get(verdict, "gray"))
    if data.get("reason"):
        st.caption(str(data["reason"]))
    with st.container(horizontal=True):
        st.metric("Expected loss", rupees(data.get("expected_loss_inr", 0.0)), border=True)
        st.metric("Spend", f"₹{data.get('spend_inr', 0.0):.2f}", border=True)
        st.metric("Tier selected", str(data.get("selected_tier")), border=True)
        st.metric(
            "Forced by the floor",
            "yes" if data.get("forced_by_conformal") else "no",
            border=True,
        )
    if data.get("response"):
        with st.container(border=True):
            st.markdown("**The response under assessment**")
            st.markdown(f"> {data['response']}")
            st.caption(f"Evidence regime: {data.get('evidence_regime', 'unknown')}")
    effects = data.get("effect_actions") or []
    if effects:
        with st.container(border=True):
            st.markdown("**Proposed effects**")
            for action in effects:
                name, effect_class, decision = str(action).split(":")
                st.markdown(f"- `{name}` · {effect_class} → **{decision.upper()}**")
    if data.get("risk"):
        st.markdown("**Calibrated harm**")
        render_harm(data["risk"])
    if data.get("policy_version"):
        st.caption(
            f"Policy {data['policy_version']} · content hash {data.get('policy_hash', '—')}"
        )


with st.container(
    horizontal=True,
    horizontal_alignment="distribute",
    vertical_alignment="center",
):
    st.title(":material/shield: ControlPlane assurance console")
    st.badge("Offline simulator", icon=":material/cloud_off:", color="violet")

st.caption(
    "The guarantee sets what may not be skipped. The allocator spends the remaining budget "
    "where expected harm is highest. All displayed numbers come from the seeded 3000-row corpus."
)

view = st.segmented_control(
    "View",
    ["Overview", "Reviewer queue", "Relearn", "Scenarios", "Decision lab", "Audit ledger"],
    default="Overview",
    required=True,
    width="stretch",
)

with st.sidebar:
    st.subheader("Global filters")
    budget_fraction = st.select_slider(
        "Budget fraction",
        options=[0.10, 0.25, 0.40, 0.60, 0.80, 1.00],
        value=0.40,
        format_func=lambda value: f"{value:.0%}",
    )
    policy_filter = st.multiselect(
        "Policies",
        ["allocator", "fixed_rate", "check_none", "check_all"],
        default=["allocator", "fixed_rate"],
    )
    st.caption("Prototype v0.3 · seeded corpus 20260824 · manifest v3")

frame, detail, scenarios = load_artifacts()

if view == "Overview":
    selected_budget = frame[frame["budget_fraction"] == budget_fraction].set_index("policy")
    allocator = selected_budget.loc["allocator"]
    compute_spend = float(allocator["assurance_spend_inr"])
    reviewer_spend = float(allocator["attention_spend_inr"])
    attention_share = reviewer_spend / (reviewer_spend + compute_spend)
    with st.container(horizontal=True):
        st.metric("Loss averted", rupees(allocator["loss_averted_inr"]), border=True)
        st.metric("Compute spend", f"₹{compute_spend:,.2f}", border=True)
        st.metric("Reviewer spend", rupees(reviewer_spend), border=True)
        st.metric(
            "Attention share of cost",
            f"{attention_share:.1%}",
            border=True,
            help="Human review against automated checking.",
        )

    left, right = st.columns([1, 1])
    with left.container(border=True):
        st.subheader("Loss averted against compute spend")
        # Long form with an explicit colour series: each policy keeps its own spend
        # values on the x axis. Pivoting on spend instead produces a table where no
        # row holds two policies at once, and the chart renders as disconnected points.
        curve = frame[frame["policy"].isin(policy_filter)][
            ["assurance_spend_inr", "loss_averted_inr", "policy"]
        ].sort_values("assurance_spend_inr")
        if curve.empty:
            st.caption("Select at least one policy in the sidebar.")
        else:
            st.line_chart(
                curve,
                x="assurance_spend_inr",
                y="loss_averted_inr",
                color="policy",
                x_label="Compute spend (INR)",
                y_label="Loss averted (INR)",
            )
            st.caption(
                "Every policy runs the same verdict rule and is charged the reviewer minutes "
                "its own verdicts raise. They differ only in which rows they check."
            )
    with right.container(border=True):
        st.subheader("Per-route release floor")
        conformal = pd.DataFrame(detail["conformal"]).T.reset_index(drop=True)
        st.dataframe(
            conformal[["route", "threshold", "upper_bound", "alpha", "released"]],
            hide_index=True,
            column_config={
                "route": "Route",
                "threshold": st.column_config.NumberColumn("Threshold", format="%.2f"),
                "upper_bound": st.column_config.NumberColumn("Certified bound", format="%.3f"),
                "alpha": st.column_config.NumberColumn("Target α", format="%.2f"),
                "released": st.column_config.NumberColumn("Released rows", format="%d"),
            },
        )
        st.caption(
            "The certified bound is what the finite-sample test guarantees. It stays under the "
            "target on every route."
        )

    with st.container(border=True):
        st.subheader("Where assurance money actually goes")
        split = frame[frame["policy"] == "allocator"][
            ["budget_fraction", "assurance_spend_inr", "attention_spend_inr"]
        ].copy()
        split["Budget"] = split["budget_fraction"].map(lambda value: f"{value:.0%}")
        split = split.rename(
            columns={
                "assurance_spend_inr": "Automated checking",
                "attention_spend_inr": "Human review",
            }
        ).set_index("Budget")
        st.bar_chart(
            split[["Human review", "Automated checking"]],
            y_label="Assurance cost (INR)",
            stack=True,
        )
        st.caption(
            "A completed review costs ₹120 against ₹3.20 for the most expensive automated check. "
            "Raising the compute budget raises the number of cases needing a person."
        )

    with st.expander("Full metric table", icon=":material/table_chart:"):
        st.dataframe(frame, hide_index=True)

elif view == "Reviewer queue":
    attention = load_attention()
    if attention is None:
        st.info("Run `make attention` to generate the reviewer-queue comparison.")
    else:
        budgets = attention["budgets"]
        chosen = next(
            (row for row in budgets if abs(row["budget_fraction"] - budget_fraction) < 1e-9),
            budgets[0],
        )
        st.subheader(f"Serving order at a {chosen['budget_fraction']:.0%} budget")
        with st.container(horizontal=True):
            st.metric("Cases raised", f"{chosen['cases_raised']:,.0f}", border=True)
            st.metric("Queue oversubscription", f"{chosen['oversubscription']:.2f}x", border=True)
            st.metric(
                "Reviewers needed to keep up",
                f"{chosen['reviewers_for_throughput']:.1f}",
                border=True,
                help=f"Against {attention['reviewers_on_shift']:.0f} on shift.",
            )
            st.metric(
                "Capacity",
                f"{attention['capacity_minutes']:,.0f} min",
                border=True,
            )

        labels = {
            "deadline_density": "deadline_density (shipped)",
            "fifo": "fifo (baseline)",
            "random": "random (baseline)",
            "density": "density (ablation)",
            "deadline": "deadline (ablation)",
        }
        rows = [
            {
                "Serving rule": labels.get(name, name),
                "Served": values["served"],
                "Shed": values["shed"],
                "SLA breaches": values["breached"],
                "Expected loss served": values["value_served_inr"],
                "High-value shed": values["high_value_shed"],
                "p99 wait (min)": values["p99_wait_minutes"],
            }
            for name, values in chosen["strategies"].items()
        ]
        queue = pd.DataFrame(rows).sort_values("Expected loss served", ascending=False)
        with st.container(border=True):
            st.dataframe(
                queue,
                hide_index=True,
                column_config={
                    "Expected loss served": st.column_config.NumberColumn(format="₹%d"),
                    "p99 wait (min)": st.column_config.NumberColumn(format="%.1f"),
                },
            )
        short = {
            "deadline_density": "ours",
            "fifo": "fifo",
            "random": "random",
            "density": "density",
            "deadline": "deadline",
        }
        plotted = pd.DataFrame(
            [
                {
                    "Rule": short.get(name, name),
                    "Expected loss served": values["value_served_inr"],
                    "SLA breaches": values["breached"],
                }
                for name, values in chosen["strategies"].items()
            ]
        ).set_index("Rule")
        left, right = st.columns(2)
        with left.container(border=True):
            st.subheader("Expected loss served")
            st.bar_chart(plotted[["Expected loss served"]], y_label="INR", horizontal=True)
        with right.container(border=True):
            st.subheader("SLA breaches")
            st.bar_chart(
                plotted[["SLA breaches"]],
                y_label="Cases past their SLA",
                horizontal=True,
            )
        st.caption(
            "Every rule serves the same number of reviews from the same cases at the same "
            "capacity, so the comparison is about ordering alone. `density` — the shipped rule "
            "with its deadline term removed — leads on both axes and is reported as such."
        )

elif view == "Scenarios":
    titles = {
        "agentic_hold": "Agentic hold — a financial action is stopped",
        "alert_fatigue": "Alert fatigue — precision against loss averted",
        "budget_shock": "Budget shock — a 40% cut mid-stream",
        "drift": "Drift — a new failure mode appears",
        "jurisdiction_switch": "Jurisdiction switch — the same request under two policies",
        "multi_turn_session": "Multi-turn — risk accumulating across a session",
    }
    scenario_name = st.selectbox(
        "Scenario",
        list(scenarios),
        format_func=lambda value: titles.get(value, value.replace("_", " ").capitalize()),
    )
    data = scenarios[scenario_name]
    st.subheader(titles.get(scenario_name, scenario_name))

    if scenario_name in {"agentic_hold", "no_ground_truth", "overlapping_harm"}:
        render_decision(data)
        if scenario_name == "no_ground_truth":
            st.caption(
                "Nothing in the context can confirm or refute this answer, so the system "
                "abstains rather than inventing a confidence it does not have. Buying more "
                "checking would spend money to learn nothing."
            )
        if scenario_name == "overlapping_harm":
            st.caption(
                f"{data.get('axes_scored_above_half', 0)} harm axes score above 0.5 against "
                f"{data.get('labelled_axes', 0)} labelled — expected loss sums across axes "
                "rather than taking the largest, because a response can be harmful in more "
                "than one way at once."
            )

    elif scenario_name == "same_response_three_routes":
        with st.container(border=True):
            st.markdown("**One response, sent down three routes**")
            st.markdown(f"> {data['response']}")
        routes = data["routes"]
        summary = pd.DataFrame(
            [
                {
                    "Route": name,
                    "Verdict": payload.get("verdict", "—"),
                    "Expected loss": payload.get("expected_loss_inr", 0.0),
                    "Tier": payload.get("selected_tier"),
                    "Forced by floor": bool(payload.get("forced_by_conformal")),
                    "Effects": ", ".join(payload.get("effect_actions") or []) or "none",
                }
                for name, payload in routes.items()
            ]
        )
        st.dataframe(
            summary,
            hide_index=True,
            column_config={"Expected loss": st.column_config.NumberColumn(format="₹%d")},
        )
        st.caption(
            "Identical text, different consequence tables. The same words are worth different "
            "amounts of checking depending on where they were said — which is the reason the "
            "system prices harm per route rather than scoring it once."
        )

    elif scenario_name == "alert_fatigue":
        comparison = pd.DataFrame(
            [
                {
                    "Policy": "allocator",
                    "Loss averted": data["allocator_loss_averted_inr"],
                    "Compute spend": data["allocator_spend_inr"],
                    "Precision": data["allocator_precision"],
                    "False positive rate": data["allocator_false_positive_rate"],
                },
                {
                    "Policy": "fixed_rate",
                    "Loss averted": data["fixed_rate_loss_averted_inr"],
                    "Compute spend": data["fixed_rate_spend_inr"],
                    "Precision": data["fixed_rate_precision"],
                    "False positive rate": data["fixed_rate_false_positive_rate"],
                },
            ]
        )
        st.dataframe(
            comparison, hide_index=True,
            column_config={
                "Loss averted": st.column_config.NumberColumn(format="₹%d"),
                "Compute spend": st.column_config.NumberColumn(format="₹%.2f"),
                "Precision": st.column_config.NumberColumn(format="%.1f%%"),
                "False positive rate": st.column_config.NumberColumn(format="%.1f%%"),
            },
        )
        st.caption(
            f"At a {data['budget_fraction']:.0%} budget. The allocator averts more loss at "
            "matched spend; the fixed-rate policy raises fewer cases and so posts higher "
            "precision on the ones it does raise."
        )

    elif scenario_name == "budget_shock":
        with st.container(horizontal=True):
            st.metric(
                "Budget cut",
                f"{data['budget_cut_percent']}%",
                border=True,
            )
            st.metric(
                "Shadow price after",
                f"{data['lambda_final_after']:.1f}",
                delta=f"{data['lambda_final_after'] - data['lambda_final_before']:+.1f}",
                border=True,
            )
            spend_delta = (
                data["spend_per_interaction_after_inr"]
                - data["spend_per_interaction_before_inr"]
            )
            st.metric(
                "Spend per interaction",
                f"₹{data['spend_per_interaction_after_inr']:.3f}",
                delta=f"{spend_delta:+.3f}",
                border=True,
            )
            st.metric(
                "Floor coverage",
                f"{data['conformal_floor_coverage_after']:.0%}",
                delta="unchanged",
                delta_color="off",
                border=True,
            )
        shock = pd.DataFrame(
            {
                "Period": ["Before cut", "After cut"],
                "High-consequence share of spend": [
                    data["high_consequence_spend_share_before"],
                    data["high_consequence_spend_share_after"],
                ],
            }
        ).set_index("Period")
        st.bar_chart(shock, y_label="Share of spend on high-consequence routes")
        st.caption(
            "The budget falls, the shadow price rises, and spend shifts towards the "
            "high-consequence routes. The release floor is untouched — its thresholds are "
            f"{data['conformal_thresholds_unchanged']}."
        )

    elif scenario_name == "drift":
        with st.container(horizontal=True):
            st.metric(
                "Tier 1 catch rate",
                f"{data['tier1_catch_rate_after']:.3f}",
                delta=f"{data['tier1_catch_rate_after'] - data['tier1_catch_rate_before']:+.3f}",
                border=True,
            )
            st.metric("Misses on the new mode", f"{data['new_failure_mode_misses']}", border=True)
            st.metric(
                "Still checked under the floor",
                "yes" if data["still_checked_under_floor"] else "no",
                border=True,
            )
        drift = pd.DataFrame(
            {
                "Period": ["Before the shift", "After the shift"],
                "Measured catch rate": [
                    data["tier1_catch_rate_before"],
                    data["tier1_catch_rate_after"],
                ],
            }
        ).set_index("Period")
        st.bar_chart(drift, y_label="Tier 1 catch rate")
        st.caption(str(data["response"]))

    elif scenario_name == "jurisdiction_switch":
        left, right = st.columns(2)
        for column, name in ((left, "eu"), (right, "india")):
            payload = data[name]
            with column.container(border=True):
                st.markdown(f"**{name.upper()}**")
                st.metric("Verdict", str(payload.get("verdict", "—")))
                st.caption(f"Policy {payload.get('policy_version', '—')}")
                effects = payload.get("effect_actions") or []
                st.markdown(
                    "**Effects:** " + (", ".join(f"`{item}`" for item in effects) or "none")
                )
        st.caption(
            "The same request under two jurisdiction policies. Consent requirements and the "
            "mandatory human-review list differ, so the effect decision can differ with no "
            "code change."
        )

    elif scenario_name == "multi_turn_session":
        if not data.get("available", False):
            st.info("Multi-turn scenario unavailable in this run.")
        else:
            with st.container(horizontal=True):
                st.metric(
                    "Turns before the check became mandatory",
                    f"{data['became_mandatory_after_turns']:.0f}",
                    border=True,
                )
                st.metric("Extra spend", f"₹{data['extra_spend_inr']:.2f}", border=True)
                st.metric("Fitted threshold", f"{data['fitted_threshold']:.2f}", border=True)
            escalation = pd.DataFrame(data["escalation"])
            st.dataframe(
                escalation, hide_index=True,
                column_config={
                    "probing_turns": st.column_config.NumberColumn("Probing turns", format="%d"),
                    "threshold_applied": st.column_config.NumberColumn(
                        "Threshold applied", format="%.3f"),
                    "session_risk": st.column_config.NumberColumn("Session risk", format="%.3f"),
                    "selected_tier": st.column_config.NumberColumn("Tier", format="%d"),
                    "forced_by_conformal": "Forced by floor",
                },
            )
            st.caption(
                "Risk carried from earlier turns is subtracted from the threshold, so history "
                "can only ever make a check mandatory — never optional."
            )

    else:
        st.json(data)

    with st.expander("Raw scenario record", icon=":material/data_object:"):
        st.json(data)

elif view == "Relearn":
    st.subheader("Refitting the calibrator from reviewer labels")
    relearn = load_relearn()
    if relearn is None:
        st.info("Run `make relearn` to refit the calibration maps from the audit chain.")
    else:
        floors = relearn["floors"]
        left, middle, right = st.columns(3)
        with left:
            st.metric("Usable labelled pairs", f"{relearn['pairs_found']:,}", border=True)
        with middle:
            st.metric(
                "Routes released",
                f"{len(relearn['accepted'])} of "
                f"{len(relearn['accepted']) + len(relearn['refused'])}",
                border=True,
            )
        with right:
            st.metric("Detector fingerprint", relearn["detector_version"], border=True)

        st.caption(
            "Only rows whose probability of being reviewed can be computed are counted: the "
            "queue's random reserve, and the fixed-rate audit of released rows. Cases the "
            "serving rule chose are excluded, because a queue ordered by expected loss picks "
            "harmful rows from inside the raised population, and no stratum-level weight undoes "
            "selection happening inside a stratum."
        )

        rows = [
            {
                "Route": route,
                "Released": "yes" if route in relearn["accepted"] else "no",
                "Why": relearn["accepted"].get(route) or relearn["refused"].get(route, ""),
            }
            for route in sorted(set(relearn["accepted"]) | set(relearn["refused"]))
        ]
        if rows:
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

        if not relearn["released"]:
            st.warning(
                "No route cleared the release gate, so the maps already serving stayed in place. "
                "That is the gate working: a refit is offered, not applied.",
                icon=":material/gpp_maybe:",
            )
        st.caption(
            f"Gate: at least {floors['min_fitting_rows']} fitting and "
            f"{floors['min_selection_rows']} selection rows, a threshold that still releases "
            f"something, calibration error at or below {floors['max_ece']}, and no regression "
            f"beyond {floors['ece_tolerance']} against the incumbent. The selection floor is "
            "derived: at alpha 0.15 with delta Bonferroni-corrected to 0.10/21, a threshold "
            "needs 33 released rows before the binomial bound can clear alpha at all."
        )

elif view == "Decision lab":
    st.subheader("Inspect one decision")
    with st.form("decision_lab"):
        route = st.segmented_control(
            "Route",
            ["support-assistant", "internal-kb", "finops-agent"],
            default="support-assistant",
            required=True,
        )
        jurisdiction = st.segmented_control(
            "Jurisdiction", ["eu", "india"], default="eu", required=True
        )
        prompt = st.text_input("Prompt", "What is the renewal fee?")
        response = st.text_area(
            "Model response", "The renewal fee is ₹9,999 and refunds are open for 90 days."
        )
        context = st.text_area(
            "Grounding context", "The renewal fee is ₹499. Refunds are allowed within 14 days."
        )
        submitted = st.form_submit_button(
            "Run decision", icon=":material/play_arrow:", type="primary"
        )
    if submitted:
        interaction = Interaction(
            interaction_id="console-decision",
            split="scenario",
            route=str(route),
            jurisdiction=str(jurisdiction),
            prompt=prompt,
            response=response,
            context_documents=[context] if context else [],
            truth=HarmVector.zeros(),
        )
        trace = assessment_engine().assess(interaction)
        color = {
            "allow": "green",
            "annotate": "blue",
            "hold": "orange",
            "abstain": "gray",
            "block": "red",
        }
        st.badge(trace.verdict, color=color[trace.verdict])
        st.caption(trace.reason)
        with st.container(horizontal=True):
            st.metric("Expected loss", f"₹{trace.expected_loss_inr:,.2f}", border=True)
            st.metric("Assurance spend", f"₹{trace.assurance_spend_inr:.2f}", border=True)
            st.metric("Selected tier", str(trace.selected_tier), border=True)
            st.metric(
                "Forced by the floor",
                "yes" if trace.forced_by_conformal else "no",
                border=True,
                help=f"Route threshold {trace.conformal_threshold:.2f}, target α "
                f"{trace.conformal_alpha:.2f}.",
            )

        left, right = st.columns(2)
        with left.container(border=True):
            st.markdown("**Calibrated harm**")
            harm = pd.DataFrame(
                sorted(trace.harm.values_by_name().items(), key=lambda item: -item[1]),
                columns=["Harm axis", "Probability"],
            )
            st.dataframe(
                harm, hide_index=True,
                column_config={"Probability": st.column_config.ProgressColumn(
                    format="%.3f", min_value=0.0, max_value=1.0)},
            )
        with right.container(border=True):
            st.markdown("**What each tier was worth**")
            tiers = pd.DataFrame(
                [
                    {
                        "Tier": choice.tier,
                        "Benefit": choice.benefit_inr,
                        "Priced cost": choice.adjusted_cost_inr,
                        "Net value": choice.net_value_inr,
                        "Chosen": choice.tier == trace.selected_tier,
                    }
                    for choice in trace.tier_decisions
                ]
            )
            st.dataframe(
                tiers, hide_index=True,
                column_config={
                    "Benefit": st.column_config.NumberColumn(format="₹%.2f"),
                    "Priced cost": st.column_config.NumberColumn(format="₹%.2f"),
                    "Net value": st.column_config.NumberColumn(format="₹%.2f"),
                },
            )
        if trace.effect_actions:
            st.markdown("**Proposed effects**")
            for action in trace.effect_actions:
                st.markdown(f"- `{action}`")
        st.caption(
            f"Policy {trace.policy_version} · content hash {trace.policy_hash} · "
            f"shadow price {trace.shadow_price:.3f}"
        )
        with st.expander("Full decision record", icon=":material/data_object:"):
            st.json(trace.model_dump(mode="json"))

else:
    ledger = LedgerStore(ROOT / "data" / "audit.db")
    valid, count = ledger.verify()
    if valid:
        st.success(f"Hash chain verified across {count} records.", icon=":material/verified:")
    else:
        st.error(f"Hash chain failed at record {count}.", icon=":material/error:")
    st.caption(
        "Each record is hashed together with the hash of the record before it, so changing any "
        "earlier row invalidates every hash that follows."
    )
    rows = ledger.records(limit=50)
    if rows:
        display = pd.DataFrame(rows).drop(columns=["record_json"])
        st.dataframe(display, hide_index=True)
        selected = st.selectbox("Inspect record", [row["sequence"] for row in rows])
        record = next(row for row in rows if row["sequence"] == selected)
        st.json(json.loads(str(record["record_json"])))
    else:
        st.caption("Run a Decision lab check or `make demo` to append audit records.")
