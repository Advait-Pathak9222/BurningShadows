from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_console_views_and_decision_lab(project_root: Path) -> None:
    console = AppTest.from_file(
        str(project_root / "console" / "streamlit_app.py"), default_timeout=60
    ).run()
    assert not console.exception
    assert [metric.label for metric in console.metric] == [
        "Assurance ROI",
        "Loss averted",
        "Intervention precision",
        "Text p99 overhead",
    ]

    for view in ("Scenarios", "Decision lab", "Audit ledger"):
        console.segmented_control[0].set_value(view).run()
        assert not console.exception

    console.segmented_control[0].set_value("Decision lab").run()
    console.button[0].click().run()
    assert not console.exception
    assert [metric.label for metric in console.metric] == [
        "Expected loss",
        "Assurance spend",
        "Selected tier",
    ]
