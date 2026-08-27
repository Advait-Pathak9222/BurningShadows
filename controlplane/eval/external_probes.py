"""Run Aegis (Pre-registration 9) and OR-Bench (Pre-registration 10) and write their results.

Both go through `corpus_probe.probe`, so their numbers are computed by the same code that
produces the synthetic-corpus report and are directly comparable with it.
"""

from __future__ import annotations

import json
from itertools import product
from pathlib import Path
from typing import Any

from controlplane.corpora import aegis, beavertails, orbench, ragtruth
from controlplane.eval.benchmark_metrics import (
    false_positive_rate_at_recall,
    within_band,
)
from controlplane.eval.corpus_probe import CorpusSpec, probe
from controlplane.eval.toxicchat_probe import write_report as write_toxicchat_report
from controlplane.models import Interaction

# Published on the Aegis test set, from the NVIDIA Aegis model card and arXiv:2404.05993.
AEGIS_PUBLISHED = {
    "Aegis LlamaGuard Defensive": {"auprc": 0.941, "f1": 0.85},
    "Aegis LlamaGuard Permissive": {"auprc": 0.941, "f1": 0.76},
    "Llama Guard Base": {"auprc": 0.930, "f1": 0.62},
    "OpenAI Mod API": {"auprc": 0.895, "f1": 0.34},
    "Perspective API": {"auprc": 0.860, "f1": 0.24},
}
AEGIS_AUPRC_BAND = (0.860, 0.941)
AEGIS_F1_BAND = (0.24, 0.85)

# Published in arXiv:2405.20947, as (safe-rejection rate, toxic-rejection rate).
ORBENCH_PUBLISHED = {
    "Claude-3-Opus": (0.910, 0.981),
    "GPT-4o": (0.067, 0.849),
    "Llama-3-70b": (0.377, 0.787),
    "Mistral-large": (0.097, 0.728),
}
ORBENCH_TARGET = ORBENCH_PUBLISHED["Llama-3-70b"]


def run_aegis(root: Path, cache_dir: Path) -> dict[str, Any]:
    """Four conditions: both label conventions, each on the shipped and text-disjoint splits."""
    results: dict[str, Any] = {"published": AEGIS_PUBLISHED}
    spec = CorpusSpec(
        name="nvidia/Aegis-AI-Content-Safety-Dataset-1.0",
        licence="CC-BY-4.0",
        source_url=(
            "https://huggingface.co/datasets/nvidia/Aegis-AI-Content-Safety-Dataset-1.0"
        ),
        labelled_axes=aegis.LABELLED_AXES,
        groups=aegis.text_types(cache_dir, "test"),
    )
    for fitted, caution, disjoint in product((False, True), repeat=3):
        calibration, _ = aegis.load(cache_dir, "train", caution_is_harm=caution)
        test, stats = aegis.load(
            cache_dir, "test", caution_is_harm=caution, text_disjoint=disjoint
        )
        result = probe(root, calibration, test, spec, fitted_tier1=fitted)
        del result["_scores"]
        result["convention"] = stats.convention
        result["text_disjoint"] = disjoint
        result["rows_overlapping_train"] = stats.rows_overlapping_train
        result["corpus"]["harm_rate"] = stats.harm_rate
        result["corpus"]["axis_rates"] = stats.axis_rates
        detection = result["detection"]
        result["endpoint"] = {
            "auprc_in_published_band": within_band(
                float(detection["auprc"]), *AEGIS_AUPRC_BAND
            ),
            "f1_in_published_band": within_band(
                float(detection["fixed_threshold"]["f1"]), *AEGIS_F1_BAND
            ),
            "auprc_band": list(AEGIS_AUPRC_BAND),
            "f1_band": list(AEGIS_F1_BAND),
        }
        key = f"{stats.convention}{'__text_disjoint' if disjoint else ''}"
        key += "__fitted" if fitted else "__lexical"
        results[key] = result
    return results


def run_orbench(root: Path, cache_dir: Path) -> dict[str, Any]:
    """Both Tier 1 conditions. The interesting output is an operating point, not a score.

    The shipped lexical detectors score AUC 0.51 here and their calibration-chosen threshold
    flags every row, so the fitted condition is what any usable number comes from.
    """
    calibration, _ = orbench.load(cache_dir, "calibration")
    test, stats = orbench.load(cache_dir, "test")
    spec = CorpusSpec(
        name="bench-llms/or-bench",
        licence="CC-BY-4.0",
        source_url="https://huggingface.co/datasets/bench-llms/or-bench",
        labelled_axes=orbench.LABELLED_AXES,
        groups=orbench.categories(cache_dir, "test"),
    )
    results: dict[str, Any] = {}
    for fitted in (False, True):
        results["fitted" if fitted else "lexical"] = _orbench_condition(
            root, calibration, test, spec, fitted
        )
    results["published"] = {
        name: {"safe_rejection": safe, "toxic_rejection": toxic}
        for name, (safe, toxic) in ORBENCH_PUBLISHED.items()
    }
    results["corpus"] = {
        "toxic_rate": stats.toxic_rate,
        "safe_rows": stats.safe,
        "toxic_rows": stats.toxic,
    }
    return results


def _orbench_condition(
    root: Path,
    calibration: list[Interaction],
    test: list[Interaction],
    spec: CorpusSpec,
    fitted: bool,
) -> dict[str, Any]:
    result = probe(root, calibration, test, spec, fitted_tier1=fitted)
    result["published"] = {
        name: {"safe_rejection": safe, "toxic_rejection": toxic}
        for name, (safe, toxic) in ORBENCH_PUBLISHED.items()
    }
    point = result["detection"]["fixed_threshold"]
    false_refusal = float(point["false_positive_rate"])
    catch = float(point["recall"])
    target_safe, target_toxic = ORBENCH_TARGET
    result["endpoint"] = {
        "target": "Llama-3-70b",
        "target_safe_rejection": target_safe,
        "target_toxic_rejection": target_toxic,
        "our_false_refusal_rate": false_refusal,
        "our_toxic_catch_rate": catch,
        "beats_on_over_refusal": false_refusal < target_safe,
        "beats_on_catch": catch >= target_toxic,
        "outcome": (
            "success"
            if false_refusal < target_safe and catch >= target_toxic
            else "partial"
            if false_refusal < target_safe or catch >= target_toxic
            else "failure"
        ),
    }
    # Published baselines each report a single (safe-rejection, catch) pair. Ours has an
    # adjustable threshold, so matching one axis and reading off the other is the only
    # like-for-like view -- and because that threshold is chosen on the split it is
    # measured on, it is an ORACLE comparison and is labelled as one everywhere it appears.
    labels = [item.truth.has_harm() for item in test]
    scores = result["_scores"]
    result["matched_recall_oracle"] = {
        name: {
            "published_safe_rejection": safe,
            "published_toxic_rejection": toxic,
            "our_false_refusal_at_their_catch": false_positive_rate_at_recall(
                labels, scores, toxic
            )[0],
        }
        for name, (safe, toxic) in ORBENCH_PUBLISHED.items()
    }
    del result["_scores"]
    return result


def run_beavertails(root: Path, cache_dir: Path) -> dict[str, Any]:
    """Both prevalences Pre-registration 7 requires: corrected to 7%, and natural.

    The natural rate is 55.8%, where flagging every row already scores F1 0.716. Reporting
    only that condition would make a weak detector look strong, which is why both are here.
    """
    results: dict[str, Any] = {}
    for label, prevalence in (("corrected_07", 0.07), ("natural", -1.0)):
        calibration, test, stats = beavertails.load(cache_dir, target_prevalence=prevalence)
        spec = CorpusSpec(
            name="PKU-Alignment/BeaverTails (round0 330k)",
            licence="CC-BY-NC-4.0",
            source_url="https://huggingface.co/datasets/PKU-Alignment/BeaverTails",
            labelled_axes=tuple(beavertails.AXIS_CATEGORIES),
            groups={},
        )
        result = probe(root, calibration, test, spec, fitted_tier1=True)
        del result["_scores"]
        result["prevalence"] = {
            "requested": prevalence if prevalence > 0 else None,
            "natural_harm_rate": stats.natural_harm_rate,
            "test_harm_rate": stats.test_harm_rate,
        }
        results[label] = result
    return results


def run_ragtruth(root: Path, cache_dir: Path) -> dict[str, Any]:
    """With and without the retrieved passages -- the pre-registered grounding control.

    The control runs the shipped lexical Tier 1, not the fitted grounding model. The fitted
    model contains an explicit early return when no context is present, so running *it*
    without context yields exactly 0.5000 by construction and proves nothing.
    """
    results: dict[str, Any] = {}
    for label, with_context in (("with_context", True), ("context_withheld", False)):
        calibration, _ = ragtruth.load(cache_dir, "train", with_context=with_context)
        test, stats = ragtruth.load(cache_dir, "test", with_context=with_context)
        spec = CorpusSpec(
            name="RAGTruth",
            licence="MIT",
            source_url="https://arxiv.org/abs/2401.00396",
            labelled_axes=("hallucination",),
            groups=ragtruth.task_types(cache_dir, "test"),
        )
        result = probe(root, calibration, test, spec, grounding_tier1=with_context)
        del result["_scores"]
        result["with_context"] = with_context
        result["corpus"]["hallucination_rate"] = stats.hallucination_rate
        results[label] = result
    return results


def _matrix_row(
    benchmark: str,
    metric: str,
    ours: float,
    null: float | None,
    published: dict[str, float],
    caveat: str,
) -> dict[str, Any]:
    """One comparable line. `null` is what a trivial policy scores on exactly these rows.

    Every headline metric on an imbalanced corpus carries its own null, because without one
    a number can sit inside a published band while being barely better than flagging
    everything -- which is what our BeaverTails and Aegis F1 figures were doing.
    """
    ranked = dict(sorted(published.items(), key=lambda item: -item[1]))
    return {
        "benchmark": benchmark,
        "metric": metric,
        "controlplane": round(ours, 4),
        "trivial_null": round(null, 4) if null is not None else None,
        "margin_over_null": round(ours - null, 4) if null is not None else None,
        "published": ranked,
        "published_band": (
            [min(published.values()), max(published.values())] if published else None
        ),
        "in_published_band": (
            min(published.values()) <= ours <= max(published.values())
            if published
            else None
        ),
        "caveat": caveat,
    }


def build_matrix(
    results: dict[str, Any], toxicchat: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """The metrics matrix, derived from the result files rather than typed by hand."""
    aegis_best = results["aegis"]["defensive__fitted"]["detection"]
    bt_natural = results["beavertails"]["natural"]["detection"]
    bt_corrected = results["beavertails"]["corrected_07"]["detection"]
    rag = results["ragtruth"]["with_context"]["detection"]
    orb = results["orbench"]["fitted"]["detection"]
    rows = []
    if toxicchat is not None:
        tc = toxicchat["all_rows__moderation_tier1"]["detection"]
        rows.append(
            _matrix_row(
                "ToxicChat (OpenAI moderation as Tier 1)",
                "AUPRC",
                float(tc["controlplane_auprc"]),
                # AUPRC's trivial null is the base rate: 7.12% here, which is why this
                # number is not comparable with the AUPRC figures on 53%-harmful corpora.
                float(tc["base_rate"]),
                {"Llama Guard Base": 0.664, "OpenAI Mod API": 0.588, "Perspective API": 0.532},
                "The Tier 1 signal is OpenAI's, not ours. We supply calibration, the floor "
                "and the allocator around it; with our lexical Tier 1 this corpus scores "
                "far lower.",
            )
        )
    return rows + [
        _matrix_row(
            "Aegis 1.0 (defensive)",
            "AUPRC",
            float(aegis_best["auprc"]),
            # For AUPRC the trivial null is the base rate: that is what a random ranker
            # scores, and on a 66%-harmful corpus it is a high bar that looks like a result.
            float(aegis_best["base_rate"]),
            {
                "Aegis LlamaGuard": 0.941,
                "Llama Guard Base": 0.930,
                "OpenAI Mod API": 0.895,
                "Perspective API": 0.860,
            },
            "Below the published band -- a failed endpoint. Fitted bag-of-words Tier 1.",
        ),
        _matrix_row(
            "BeaverTails (natural, 55.8% harm)",
            "F1",
            float(bt_natural["fixed_threshold"]["f1"]),
            float(bt_natural["flag_everything_f1"]),
            {"published band high": 0.839, "published band low": 0.364},
            "At this base rate the margin over flagging everything is the only real signal.",
        ),
        _matrix_row(
            "BeaverTails (prevalence-corrected, 7% harm)",
            "F1",
            float(bt_corrected["fixed_threshold"]["f1"]),
            float(bt_corrected["flag_everything_f1"]),
            {"published band high": 0.839, "published band low": 0.364},
            "The deployment-realistic prevalence, and far harder than the natural rate.",
        ),
        _matrix_row(
            "RAGTruth",
            "F1",
            float(rag["fixed_threshold"]["f1"]),
            float(rag["flag_everything_f1"]),
            {
                "LettuceDetect large": 0.7922,
                "Fine-tuned Llama-2-13B": 0.787,
                "Luna": 0.654,
                "GPT-4 Turbo prompting": 0.634,
                "RAGAS Faithfulness": 0.520,
            },
            "Threshold chosen on calibration and applied unchanged. Fitted grounding Tier 1.",
        ),
        _matrix_row(
            "OR-Bench",
            "AUC",
            float(orb["auc"]),
            0.5,
            {},
            "Over-refusal benchmark; the operating point matters more than the AUC.",
        ),
    ]


def _fmt(value: object, spec: str = ".4f") -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int | float):
        return format(float(value), spec)
    return str(value)


def _conditions(payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [
        (name, value)
        for name, value in sorted(payload.items())
        if isinstance(value, dict) and "detection" in value
    ]


def render_benchmarks(results: dict[str, Any], matrix: list[dict[str, Any]]) -> str:
    """Generate `benchmarks.md`, so the prose cannot drift away from the numbers."""
    lines = [
        "# Metrics matrix: how we compare against published numbers",
        "",
        "**Generated by `make benchmarks`. Do not edit by hand.**",
        "",
        "Every figure below is computed from the result files in this directory, which the same",
        "command writes. Nothing on this page is typed in.",
        "",
        "## Read the null column first",
        "",
        "On an imbalanced corpus a respectable-looking F1 can be barely better than a policy that",
        "flags every single row. `trivial null` is what flagging everything scores on exactly",
        "these rows; `margin` is what our detector adds. A large F1 with a small margin is a",
        "statement about the base rate, not about detection.",
        "",
        "| Benchmark | Metric | Ours | Trivial null | Margin | Published band | In band |",
        "|---|---|---:|---:|---:|---|:--:|",
    ]
    for row in matrix:
        band = row["published_band"]
        band_text = f"{band[0]:.3f} - {band[1]:.3f}" if band else "--"
        in_band = _fmt(row["in_published_band"]) if band else "--"
        lines.append(
            f"| {row['benchmark']} | {row['metric']} | **{_fmt(row['controlplane'])}** | "
            f"{_fmt(row['trivial_null'])} | {_fmt(row['margin_over_null'], '+.4f')} | "
            f"{band_text} | {in_band} |"
        )

    lines += ["", "### What each row does not say", ""]
    for row in matrix:
        lines.append(f"- **{row['benchmark']}** — {row['caveat']}")

    lines += [
        "",
        "## Which Tier 1 produced each number",
        "",
        "Several of these use a detector fitted on the benchmark rather than the shipped lexical",
        "rules, and that is stated per row because it changes what the number means. The shipped",
        "Tier 0 and Tier 1 are lexical stubs written against our own corpus. `fitted_bayes_bow`",
        "and `fitted_grounding` are **evaluation adapters**: they are fitted on the calibration",
        "fold of the corpus under test and are not wired into the serving path.",
        "",
        "| Result | Tier 1 in use |",
        "|---|---|",
    ]
    for name, payload in sorted(results.items()):
        for condition, result in _conditions(payload):
            lines.append(f"| {name} / {condition} | `{result['tier1']}` |")

    lines += [
        "",
        "## Detection, every condition",
        "",
        "| Result | Rows | Base rate | AUC | AUPRC | F1 | Null | Degenerate |",
        "|---|---:|---:|---:|---:|---:|---:|:--:|",
    ]
    for name, payload in sorted(results.items()):
        for condition, result in _conditions(payload):
            detection = result["detection"]
            point = detection["fixed_threshold"]
            lines.append(
                f"| {name} / {condition} | {result['corpus']['test_rows']} | "
                f"{_fmt(detection['base_rate'])} | {_fmt(detection['auc'])} | "
                f"{_fmt(detection['auprc'])} | {_fmt(point['f1'])} | "
                f"{_fmt(detection['flag_everything_f1'])} | {_fmt(point['degenerate'])} |"
            )

    lines += [
        "",
        "A **degenerate** operating point flags every row or none, so its F1 describes the corpus",
        "rather than the detector.",
        "",
        "## Conformal validation, and where it is vacuous",
        "",
        "| Result | Released unchecked | Observed rate | Holds | Vacuous |",
        "|---|---:|---:|:--:|:--:|",
    ]
    for name, payload in sorted(results.items()):
        for condition, result in _conditions(payload):
            for route, value in sorted(result["conformal_validation"].items()):
                lines.append(
                    f"| {name} / {condition} ({route}) | {value['released']:.0f} | "
                    f"{_fmt(value['observed_rate'])} | {_fmt(value['holds'])} | "
                    f"{_fmt(value['vacuous'])} |"
                )

    lines += [
        "",
        "A **vacuous** bound is one where the floor forced a check on every row: nothing was",
        "released unchecked, so the guarantee is satisfied by construction and carries no",
        "information. The floor is informative only when alpha exceeds the corpus harm base rate.",
        "",
        "## Allocation at matched actual spend",
        "",
        "| Result | Allocator wins | Budgets tested | Spearman(risk, expected loss) |",
        "|---|---:|---:|---:|",
    ]
    for name, payload in sorted(results.items()):
        for condition, result in _conditions(payload):
            lines.append(
                f"| {name} / {condition} | {result['allocator_wins']} | "
                f"{result['budgets_tested']} | "
                f"{_fmt(result['harm_mix']['spearman_risk_expected_loss'], '.6f')} |"
            )

    lines += [
        "",
        "## Reproducing this",
        "",
        "```bash",
        "make benchmarks    # writes every JSON in this directory, and this file",
        "```",
        "",
        "The first run downloads each corpus into `data/external/` at the revision pinned in",
        "`controlplane/corpora/*.py` and verifies its SHA-256 before use. `make demo` never",
        "touches the network.",
        "",
    ]
    return "\n".join(lines)


def render_comparison_figure(matrix: list[dict[str, Any]], path: Path) -> Path:
    """Draw the benchmark comparison from the matrix, so the figure cannot go stale.

    The previous version of this image was drawn by hand and kept a ToxicChat AUPRC of
    0.662 long after the pipeline produced 0.597 -- a figure presented as evidence while
    disagreeing with every file behind it. It is generated now, from the same matrix that
    writes `benchmarks.md`.

    The **trivial null** is drawn as a hatched bar behind each score, because on these
    corpora it is often most of the height and a bar chart without it flatters us badly.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = list(reversed(matrix))
    labels = [f"{row['benchmark']}\n({row['metric']})" for row in rows]
    ours = [float(row["controlplane"]) for row in rows]
    nulls = [
        float(row["trivial_null"]) if row["trivial_null"] is not None else 0.0
        for row in rows
    ]

    figure, axes = plt.subplots(figsize=(11, 5.0))
    positions = range(len(rows))
    axes.barh(
        list(positions), nulls, height=0.62, color="#d7d2cb",
        hatch="///", edgecolor="#9a938a", label="Trivial null (flag everything / base rate)",
    )
    axes.barh(
        list(positions), ours, height=0.30, color="#1f5c8b", label="ControlPlane",
    )
    for index, row in enumerate(rows):
        band = row["published_band"]
        if band:
            axes.plot(
                [band[0], band[1]], [index + 0.34, index + 0.34],
                color="#b4531f", linewidth=2.4, solid_capstyle="butt",
            )
            axes.plot(
                [band[0], band[1]], [index + 0.34, index + 0.34],
                "|", color="#b4531f", markersize=8,
            )
        axes.text(
            float(row["controlplane"]) + 0.012, index,
            f"{float(row['controlplane']):.3f}",
            va="center", ha="left", fontsize=9, color="#12324a",
        )

    axes.plot([], [], color="#b4531f", linewidth=2.4, label="Published range on that benchmark")
    axes.set_yticks(list(positions))
    axes.set_yticklabels(labels, fontsize=9)
    axes.set_xlim(0.0, 1.05)
    axes.set_xlabel("Score (metric differs per row; read each row against its own null and band)")
    axes.set_title(
        "ControlPlane against published detectors, with the trivial null shown",
        fontsize=12, pad=12,
    )
    axes.legend(loc="lower right", fontsize=8, framealpha=0.95)
    axes.spines[["top", "right"]].set_visible(False)
    axes.grid(axis="x", color="#e6e2dc", linewidth=0.8)
    axes.set_axisbelow(True)
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Pin the metadata so repeated runs produce identical bytes and a clean clone stays clean.
    figure.savefig(path, dpi=150, metadata={"Software": None, "Creation Time": None})
    plt.close(figure)
    return path


def write_reports(root: Path, cache_dir: Path) -> list[Path]:
    """Write every external-corpus artifact. One command, and no hand-written numbers."""
    out = root / "docs" / "results"
    out.mkdir(parents=True, exist_ok=True)
    # ToxicChat runs here too, so that one command really does produce every external
    # result. Its probe has a different shape (four pre-registered conditions rather than a
    # corpus spec), so it writes its own file and is folded into the matrix separately.
    toxicchat_path = write_toxicchat_report(root, cache_dir)
    results = {
        "aegis": run_aegis(root, cache_dir),
        "beavertails": run_beavertails(root, cache_dir),
        "orbench": run_orbench(root, cache_dir),
        "ragtruth": run_ragtruth(root, cache_dir),
    }
    written: list[Path] = [toxicchat_path]
    for name, payload in results.items():
        path = out / f"{name}.json"
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
            newline="\n",
        )
        written.append(path)

    toxicchat = json.loads(toxicchat_path.read_text(encoding="utf-8"))
    matrix = build_matrix(results, toxicchat)
    matrix_path = out / "metrics_matrix.json"
    matrix_path.write_text(
        json.dumps(matrix, indent=2, sort_keys=True, default=str), encoding="utf-8", newline="\n"
    )
    written.append(matrix_path)

    written.append(
        render_comparison_figure(matrix, root / "docs" / "images" / "benchmark-comparison.png")
    )

    benchmarks_path = out / "benchmarks.md"
    benchmarks_path.write_text(render_benchmarks(results, matrix), encoding="utf-8", newline="\n")
    written.append(benchmarks_path)
    return written
