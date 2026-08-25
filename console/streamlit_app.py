from __future__ import annotations

import json
from pathlib import Path

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
def load_artifacts() -> tuple[pd.DataFrame, dict[str, object], dict[str, object]]:
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


@st.cache_resource
def assessment_engine() -> AssessmentEngine:
    interactions = ensure_corpus(ROOT / "data")
    runtime = AssessmentEngine(ROOT, ledger_path=ROOT / "data" / "audit.db")
    runtime.calibrate(
        [interaction for interaction in interactions if interaction.split == "calibration"]
    )
    return runtime


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
    ["Overview", "Scenarios", "Decision lab", "Audit ledger"],
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
    with st.container(horizontal=True):
        st.metric(
            "Assurance ROI",
            f"{allocator['assurance_roi']:.1f}x",
            border=True,
        )
        st.metric(
            "Loss averted",
            f"₹{allocator['loss_averted_inr']:,.0f}",
            border=True,
        )
        st.metric(
            "Intervention precision",
            f"{allocator['intervention_precision']:.1%}",
            border=True,
        )
        st.metric(
            "Text p99 overhead",
            f"{allocator['p99_text_latency_ms']:.0f} ms",
            border=True,
        )

    curve = frame[frame["policy"].isin(policy_filter)].pivot_table(
        index="assurance_spend_inr",
        columns="policy",
        values="loss_averted_inr",
    )
    left, right = st.columns([3, 2])
    with left.container(border=True):
        st.subheader("Loss averted vs assurance spend")
        st.line_chart(curve, x_label="Assurance spend (INR)", y_label="Loss averted (INR)")
    with right.container(border=True):
        st.subheader("Per-route guarantee floor")
        conformal = pd.DataFrame(detail["conformal"]).T.reset_index(drop=True)
        st.dataframe(
            conformal[["route", "threshold", "upper_bound", "alpha", "released"]],
            hide_index=True,
            column_config={
                "threshold": st.column_config.NumberColumn(format="%.2f"),
                "upper_bound": st.column_config.NumberColumn(format="%.3f"),
                "alpha": st.column_config.NumberColumn(format="%.2f"),
            },
        )

    with st.expander("Metric table", icon=":material/table_chart:"):
        st.dataframe(frame, hide_index=True)

elif view == "Scenarios":
    scenario_name = st.selectbox(
        "Scenario",
        list(scenarios),
        format_func=lambda value: value.replace("_", " ").capitalize(),
    )
    with st.container(border=True):
        st.subheader(scenario_name.replace("_", " ").capitalize())
        st.json(scenarios[scenario_name])
    if scenario_name == "budget_shock":
        shock = scenarios[scenario_name]
        shock_frame = pd.DataFrame(
            {
                "period": ["Before cut", "After cut"],
                "coverage": [shock["coverage_before"], shock["coverage_after"]],
            }
        )
        st.bar_chart(shock_frame, x="period", y="coverage", y_label="Checked share")

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
        with st.container(horizontal=True):
            st.metric("Expected loss", f"₹{trace.expected_loss_inr:,.2f}", border=True)
            st.metric("Assurance spend", f"₹{trace.assurance_spend_inr:.2f}", border=True)
            st.metric("Selected tier", str(trace.selected_tier), border=True)
        st.json(trace.model_dump(mode="json"))

else:
    ledger = LedgerStore(ROOT / "data" / "audit.db")
    valid, count = ledger.verify()
    if valid:
        st.success(f"Hash chain verified across {count} records.", icon=":material/verified:")
    else:
        st.error(f"Hash chain failed at record {count}.", icon=":material/error:")
    rows = ledger.records(limit=50)
    if rows:
        display = pd.DataFrame(rows).drop(columns=["record_json"])
        st.dataframe(display, hide_index=True)
        selected = st.selectbox("Inspect record", [row["sequence"] for row in rows])
        record = next(row for row in rows if row["sequence"] == selected)
        st.json(json.loads(str(record["record_json"])))
    else:
        st.caption("Run a Decision lab check or `make demo` to append audit records.")
