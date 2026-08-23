from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from controlplane.eval.report import build_report
from controlplane.ledger import LedgerStore
from controlplane.service import AssessmentEngine
from controlplane.sim.scenarios import run_scenarios
from controlplane.sim.traffic import ensure_corpus, generate_corpus, write_corpus

ROOT = Path(__file__).resolve().parents[1]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="controlplane")
    parser.add_argument("command", choices=("data", "demo", "report", "clean"))
    args = parser.parse_args(argv)
    if args.command == "data":
        interactions = generate_corpus()
        write_corpus(interactions, ROOT / "data")
        print(f"Wrote {len(interactions)} labelled interactions to data/.")
        return 0
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
