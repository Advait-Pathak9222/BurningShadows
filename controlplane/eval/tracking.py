from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd

EXPERIMENT = "controlplane-r2"
STORE_DIR = "mlruns"
PARAM_COLUMNS = ("policy", "budget_fraction")
SKIP_METRICS = frozenset({"policy", "budget_fraction"})


def tracking_enabled() -> bool:
    """Tracking is bookkeeping; the offline demo must not require it."""
    if os.environ.get("CONTROLPLANE_TRACKING", "auto") == "off":
        return False
    try:
        import mlflow  # noqa: F401
    except ImportError:
        return False
    return True


def _store_uri(root: Path) -> str:
    """A serverless local store is the point, so opt in to the file backend explicitly.

    MLflow 3 puts the plain-directory store in maintenance mode and asks for a database
    instead, but its model registry still refuses a sqlite URI. A file store under
    ./mlruns needs no server and no migration, which is what two people on two machines
    comparing runs actually need here.
    """
    store = root / STORE_DIR
    store.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
    return store.as_uri()


def log_evaluation(root: Path, frame: pd.DataFrame, detail: dict[str, Any]) -> int:
    """Write one MLflow run per (policy, budget) so variants compare across tools."""
    if not tracking_enabled():
        return 0
    import mlflow

    mlflow.set_tracking_uri(_store_uri(root))
    mlflow.set_experiment(EXPERIMENT)
    shared = _shared_params(root, detail)
    logged = 0
    for record in frame.to_dict(orient="records"):
        _log_run(mlflow, record, shared, detail, root)
        logged += 1
    return logged


def _log_run(
    mlflow: Any,
    record: dict[str, Any],
    shared: dict[str, Any],
    detail: dict[str, Any],
    root: Path,
) -> None:
    policy = str(record["policy"])
    fraction = float(record["budget_fraction"])
    with mlflow.start_run(run_name=f"{policy}@{fraction:.2f}"):
        mlflow.set_tags({"author": "claude-code", "milestone": "phase-b", "policy": policy})
        mlflow.log_params(
            shared
            | {
                "policy": policy,
                "budget_fraction": fraction,
                "budget_rate_inr": detail["full_check_spend_inr"] * fraction,
                "shadow_price_final": detail["shadow_price"].get(f"{fraction:.2f}", 0.0),
            }
        )
        mlflow.log_metrics(
            {
                key: float(value)
                for key, value in record.items()
                if key not in SKIP_METRICS and isinstance(value, int | float)
            }
        )
        _log_conformal(mlflow, detail)
        _log_audit(mlflow, detail, fraction)
        if policy == "allocator" and fraction == 1.0:
            _log_artifacts(mlflow, root)


def _log_conformal(mlflow: Any, detail: dict[str, Any]) -> None:
    for route, values in detail["conformal_validation"].items():
        mlflow.log_metrics(
            {
                f"conformal_observed_rate.{route}": float(values["observed_rate"]),
                f"conformal_upper_bound.{route}": float(values["observed_upper_bound"]),
                f"conformal_holds.{route}": float(bool(values["holds"])),
            }
        )
    for route, values in detail["reliability"].items():
        mlflow.log_metric(f"ece.{route}", float(values["ece"]))


def _log_audit(mlflow: Any, detail: dict[str, Any], fraction: float) -> None:
    audit = detail["audit"].get(f"{fraction:.2f}") or next(
        iter(detail["audit"].values()), None
    )
    if audit is None:
        return
    mlflow.log_metrics(
        {
            "audit_coverage": float(audit["coverage"]),
            "audit_chain_valid": float(bool(audit["chain_valid"])),
        }
    )


def _log_artifacts(mlflow: Any, root: Path) -> None:
    for relative in (
        "reports/figures/loss_averted_vs_spend.png",
        "reports/figures/reliability_by_route.png",
        "reports/evaluation.csv",
        "reports/scenarios.json",
    ):
        path = root / relative
        if path.exists():
            mlflow.log_artifact(str(path))


def _shared_params(root: Path, detail: dict[str, Any]) -> dict[str, Any]:
    conformal = detail["conformal"]
    first = next(iter(conformal.values()))
    return {
        "alpha": first["alpha"],
        "delta": first["delta"],
        "seed": 20260823,
        "corpus_version": _manifest_version(root),
        "git_sha": _git_sha(root),
        "tier_costs_inr": "0.02/0.18/3.20",
        "routes": "support-assistant,internal-kb,finops-agent",
    }


def _manifest_version(root: Path) -> str:
    manifest = root / "data" / "dataset_manifest.yaml"
    if not manifest.exists():
        return "unknown"
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if line.startswith("manifest_version:"):
            return line.split(":", 1)[1].strip()
    return "unknown"


def _git_sha(root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return completed.stdout.strip()
