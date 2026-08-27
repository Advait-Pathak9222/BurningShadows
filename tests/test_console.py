from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_console_views_and_decision_lab(project_root: Path) -> None:
    console = AppTest.from_file(
        str(project_root / "console" / "streamlit_app.py"), default_timeout=90
    ).run()
    assert not console.exception
    assert [metric.label for metric in console.metric] == [
        "Loss averted",
        "Compute spend",
        "Reviewer spend",
        "Attention share of cost",
    ]

    for view in ("Reviewer queue", "Scenarios", "Decision lab", "Audit ledger"):
        console.segmented_control[0].set_value(view).run()
        assert not console.exception, f"{view} raised {console.exception}"

    console.segmented_control[0].set_value("Decision lab").run()
    console.button[0].click().run()
    assert not console.exception
    assert [metric.label for metric in console.metric] == [
        "Expected loss",
        "Assurance spend",
        "Selected tier",
        "Forced by the floor",
    ]


def test_every_scenario_renders_without_falling_back_to_raw_json(project_root: Path) -> None:
    """Each scenario has a hand-written view; a new one must not slip through unstyled."""
    console = AppTest.from_file(
        str(project_root / "console" / "streamlit_app.py"), default_timeout=90
    ).run()
    console.segmented_control[0].set_value("Scenarios").run()
    assert not console.exception

    options = list(console.selectbox[0].options)
    assert options, "no scenarios were loaded"
    for scenario in options:
        console.selectbox[0].set_value(scenario).run()
        assert not console.exception, f"{scenario} raised {console.exception}"
        # One `st.json` is the deliberate raw-record expander. A second means the
        # scenario fell through to the unstyled branch.
        assert len(console.json) == 1, f"{scenario} is not rendered as a styled view"


def test_overview_chart_has_a_point_for_every_policy_and_budget(project_root: Path) -> None:
    """Guards the defect where pivoting on spend left no row holding two policies at once."""
    import pandas as pd

    frame = pd.read_csv(project_root / "reports" / "evaluation.csv")
    selected = frame[frame["policy"].isin(["allocator", "fixed_rate"])]
    curve = selected[["assurance_spend_inr", "loss_averted_inr", "policy"]]
    assert not curve.isna().to_numpy().any()
    for policy in ("allocator", "fixed_rate"):
        assert len(curve[curve["policy"] == policy]) == frame["budget_fraction"].nunique()
