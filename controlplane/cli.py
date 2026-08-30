from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from controlplane.eval.attention import run_attention, write_attention
from controlplane.eval.judge_probe import run_probe, write_probe
from controlplane.eval.loadtest import run_loadtest
from controlplane.eval.report import build_report
from controlplane.eval.sensitivity import run_sensitivity, write_sensitivity
from controlplane.ledger import LedgerStore
from controlplane.service import AssessmentEngine
from controlplane.sim.scenarios import run_scenarios
from controlplane.sim.traffic import ensure_corpus, generate_corpus, write_corpus

ROOT = Path(__file__).resolve().parents[1]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="controlplane")
    parser.add_argument(
        "command",
        choices=(
            "data",
            "demo",
            "report",
            "sensitivity",
            "attention",
            "pii-probe",
            "judge-probe",
            "loadtest",
            "toxicchat",
            "benchmarks",
            "relearn",
            "clean",
        ),
    )
    args = parser.parse_args(argv)
    if args.command == "data":
        interactions = generate_corpus()
        write_corpus(interactions, ROOT / "data")
        print(f"Wrote {len(interactions)} labelled interactions to data/.")
        return 0
    if args.command == "sensitivity":
        interactions = ensure_corpus(ROOT / "data")
        summary = run_sensitivity(ROOT, interactions)
        write_sensitivity(ROOT, summary)
        print(
            f"Decisions that flip across the consequence range: "
            f"{summary['flip_rate']:.1%} (stop condition {summary['stop_condition']:.0%})."
        )
        return 0 if summary["flip_rate"] <= summary["stop_condition"] else 1
    if args.command == "attention":
        interactions = ensure_corpus(ROOT / "data")
        summary = run_attention(ROOT, interactions)
        write_attention(ROOT, summary)
        verdict = summary["verdict"]
        print(
            f"Attention allocation vs FIFO: {verdict['outcome'].upper()} "
            f"({verdict['budgets_dominated']:.0f} of "
            f"{verdict['budgets_total']:.0f} budgets dominated)."
        )
        return 0 if verdict["outcome"] != "failure" else 1
    if args.command == "pii-probe":
        from controlplane.eval.pii_probe import run_pii_probe, write_pii_probe

        summary = run_pii_probe(ROOT)
        write_pii_probe(ROOT, summary)
        print(
            f"PII axis: Tier 0 AUC {summary['tier0']['auc']:.4f} "
            f"(F1 {summary['tier0']['f1']:.4f}) against a shape-only ceiling of "
            f"{summary['shape_ceiling']:.4f}; presidio AUC "
            f"{summary['presidio']['auc']:.4f}."
        )
        return 0
    if args.command == "judge-probe":
        summary = run_probe(ROOT)
        write_probe(ROOT, summary)
        print(
            f"{summary['model']}: stub AUC {summary['auc_stub_whole_response']:.4f}, "
            f"judge AUC {summary['auc_judge_whole_response']:.4f}, "
            f"page-max AUC {summary['auc_judge_page_max']:.4f}, "
            f"localisation {summary['localisation_rate']:.1%}"
        )
        return 0
    if args.command == "toxicchat":
        from controlplane.eval.toxicchat_probe import write_report

        report_path = write_report(ROOT, ROOT / "data" / "external")
        print(f"Wrote {report_path.relative_to(ROOT)}.")
        return 0
    if args.command == "benchmarks":
        from controlplane.eval.external_probes import write_reports

        for path in write_reports(ROOT, ROOT / "data" / "external"):
            print(f"Wrote {path.relative_to(ROOT)}.")
        return 0
    if args.command == "loadtest":
        report_path = run_loadtest(ROOT)
        print(f"Wrote {report_path.relative_to(ROOT)}.")
        return 0
    if args.command == "relearn":
        return _relearn()
    if args.command == "report":
        interactions = ensure_corpus(ROOT / "data")
        frame, _ = build_report(ROOT, interactions)
        print(frame.to_string(index=False))
        print("Wrote reports/evaluation.md and reports/figures/loss_averted_vs_spend.png.")
        return 0
    if args.command == "demo":
        interactions = ensure_corpus(ROOT / "data")
        frame, _ = build_report(ROOT, interactions)
        engine = AssessmentEngine(ROOT, ledger_path=ROOT / "data" / "audit.db")
        # Start each demo from an empty chain so the record count describes this run.
        assert engine.ledger is not None
        engine.ledger.reset()
        engine.calibrate([item for item in interactions if item.split == "calibration"])
        scenarios = run_scenarios(ROOT, engine, interactions, frame)
        ledger = LedgerStore(ROOT / "data" / "audit.db")
        chain_ok, records = ledger.verify()
        ledger.close()
        print(json.dumps(scenarios, indent=2, default=str))
        print(f"Audit chain valid: {chain_ok} ({records} records checked)")
        return 0 if chain_ok else 1
    _clean_generated_files()
    return 0


def _relearn() -> int:
    """Refit the calibration maps from reviewer labels already in the audit chain."""
    from controlplane.eval.report import recorded_chain_path
    from controlplane.learning import (
        collect_labelled_scores,
        latest_artifact,
        refit_calibration,
        write_artifact,
        write_refit_report,
    )

    # The scenario chain in data/ carries decisions only. Reviews are written by the
    # evaluation run, so that is the chain a refit can join scores to labels from.
    ledger_path = recorded_chain_path(ROOT)
    if not ledger_path.exists():
        print(f"No audit chain at {ledger_path.relative_to(ROOT)}; run `make report` first.")
        return 1

    engine = AssessmentEngine(ROOT, ledger_path=ledger_path)
    assert engine.ledger is not None
    rows = collect_labelled_scores(engine.ledger, engine.cost_model)
    fingerprint = engine.detector_fingerprint()
    outcome = refit_calibration(
        rows,
        engine.policy_store,
        fingerprint,
        incumbent=latest_artifact(ROOT, fingerprint),
    )
    engine.ledger.close()

    print(f"Labelled pairs joined from the chain: {outcome.pairs_found}")
    for route, reason in sorted(outcome.accepted.items()):
        print(f"  accepted  {route}: {reason}")
    for route, reason in sorted(outcome.refused.items()):
        print(f"  REFUSED   {route}: {reason}")
    for path in write_refit_report(ROOT, outcome, fingerprint):
        print(f"Wrote {path.relative_to(ROOT)}.")
    if outcome.artifact is None:
        # Not an error. Refusing to ship a map is the gate working, and the previous
        # artifact keeps serving.
        print("No route cleared the release gate; nothing written.")
        return 0
    path = write_artifact(outcome.artifact, ROOT)
    print(f"Wrote {path.relative_to(ROOT)} for detector {fingerprint}.")
    return 0


def _clean_generated_files() -> None:
    targets = [
        ROOT / "data" / "interactions.jsonl",
        ROOT / "data" / "calibration.jsonl",
        ROOT / "data" / "test.jsonl",
        ROOT / "data" / "audit.db",
        ROOT / "reports" / "evaluation.csv",
        ROOT / "reports" / "evaluation.json",
        ROOT / "reports" / "evaluation.md",
        ROOT / "reports" / "scenarios.json",
        ROOT / "reports" / "figures" / "loss_averted_vs_spend.png",
    ]
    for path in targets:
        if path.exists() and path.is_file():
            path.unlink()
    print("Removed generated corpus, report, and ledger files.")


if __name__ == "__main__":
    raise SystemExit(main())
