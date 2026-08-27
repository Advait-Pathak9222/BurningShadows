from __future__ import annotations

import json
import random
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import yaml

from controlplane.detectors.ollama_judge import JudgeConfig, OllamaJudge
from controlplane.models import Interaction
from controlplane.service import AssessmentEngine
from controlplane.sim.traffic import load_interactions

SENTENCE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class RowResult:
    interaction_id: str
    route: str
    true_harm: bool
    whole_score: float
    page_score: float
    stub_score: float
    localised: bool | None
    seconds: float


def sentences(interaction: Interaction) -> list[tuple[int, int, str]]:
    """Split on sentence boundaries, keeping exact offsets into the response."""
    spans: list[tuple[int, int, str]] = []
    cursor = 0
    for part in SENTENCE.split(interaction.response):
        if not part.strip():
            continue
        start = interaction.response.index(part, cursor)
        spans.append((start, start + len(part), part))
        cursor = start + len(part)
    return spans


def sample_rows(rows: list[Interaction], size: int, seed: int) -> list[Interaction]:
    """Half harmful, half clean, so localisation has enough positives to measure."""
    rng = random.Random(seed)
    harmful = [row for row in rows if row.truth.has_harm()]
    clean = [row for row in rows if not row.truth.has_harm()]
    half = size // 2
    return rng.sample(harmful, min(half, len(harmful))) + rng.sample(
        clean, min(size - half, len(clean))
    )


def run_probe(root: Path) -> dict[str, Any]:
    settings = yaml.safe_load((root / "config" / "judge.yaml").read_text(encoding="utf-8"))
    config = JudgeConfig.load(root / "config" / "judge.yaml")
    test = load_interactions(root / "data" / "test.jsonl")
    rows = sample_rows(test, int(settings["sample_rows"]), config.seed)

    engine = AssessmentEngine(root)
    engine.calibrate(load_interactions(root / "data" / "calibration.jsonl"))
    judge = OllamaJudge(config)

    started = perf_counter()
    with ThreadPoolExecutor(max_workers=int(settings["concurrency"])) as pool:
        results = list(pool.map(lambda row: _score_row(row, judge, engine), rows))
    judge.close()
    elapsed = perf_counter() - started
    return _summarise(results, config, elapsed)


def _score_row(row: Interaction, judge: OllamaJudge, engine: AssessmentEngine) -> RowResult:
    started = perf_counter()
    source = " ".join(row.context_documents or row.comparison_samples) or "(none supplied)"
    whole = judge.score_spans([row.response], source)[0]
    pages = sentences(row)
    page_scores = judge.score_spans([text for _, _, text in pages], source)
    best = max(range(len(pages)), key=lambda i: page_scores[i].maximum()) if pages else -1
    return RowResult(
        interaction_id=row.interaction_id,
        route=row.route,
        true_harm=row.truth.has_harm(),
        whole_score=whole.maximum(),
        page_score=max((score.maximum() for score in page_scores), default=0.0),
        stub_score=engine.detect(row).harm.maximum(),
        localised=_localised(row, pages, best),
        seconds=perf_counter() - started,
    )


def _localised(
    row: Interaction, pages: list[tuple[int, int, str]], best: int
) -> bool | None:
    """Did the highest-scoring page overlap a labelled harmful span?"""
    if not row.spans or best < 0:
        return None
    start, end, _ = pages[best]
    return any(start < span.end and span.start < end for span in row.spans)


def _auc(scores: list[float], labels: list[bool]) -> float:
    positive = [score for score, label in zip(scores, labels, strict=True) if label]
    negative = [score for score, label in zip(scores, labels, strict=True) if not label]
    if not positive or not negative:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in positive for n in negative)
    return wins / (len(positive) * len(negative))


def _summarise(
    results: list[RowResult], config: JudgeConfig, elapsed: float
) -> dict[str, Any]:
    labels = [row.true_harm for row in results]
    localised = [row.localised for row in results if row.localised is not None]
    return {
        "model": config.model,
        "rows": len(results),
        "wall_seconds": elapsed,
        "seconds_per_row": elapsed / len(results) if results else 0.0,
        "auc_stub_whole_response": _auc([r.stub_score for r in results], labels),
        "auc_judge_whole_response": _auc([r.whole_score for r in results], labels),
        "auc_judge_page_max": _auc([r.page_score for r in results], labels),
        "localisation_rate": sum(localised) / len(localised) if localised else 0.0,
        "localisation_n": len(localised),
        "rows_detail": [vars(row) for row in results],
    }


def write_probe(root: Path, summary: dict[str, Any]) -> None:
    results_dir = root / "docs" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "judge_probe.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str), encoding="utf-8", newline="\n"
    )
    lines = [
        "# Local judge probe",
        "",
        f"Model `{summary['model']}` over {summary['rows']} held-out rows, half of them",
        "carrying a labelled harmful span. Regenerated by `make judge-probe`; it needs a",
        "running Ollama and is never on the `make demo` path.",
        "",
        "## Does a real judge rank harm better than the offline stub?",
        "",
        "| Scorer | AUC |",
        "|---|---:|",
        f"| stub detectors, whole response | {summary['auc_stub_whole_response']:.4f} |",
        f"| {summary['model']}, whole response | {summary['auc_judge_whole_response']:.4f} |",
        f"| {summary['model']}, best single page | {summary['auc_judge_page_max']:.4f} |",
        "",
        "## Does it find the right clause?",
        "",
        f"The highest-scoring page overlapped the labelled harmful span in "
        f"**{summary['localisation_rate']:.1%}** of {summary['localisation_n']} harmful rows.",
        "",
        "Paging only pays if the judge can be sent a subset of a response without losing the",
        "harm, so this number decides whether paged verification is viable at all.",
        "",
        "## Cost",
        "",
        f"- {summary['wall_seconds']:.0f}s wall clock, {summary['seconds_per_row']:.1f}s per row",
        "- two calls per row: one whole-response, one batch covering every page",
        "",
    ]
    (results_dir / "judge_probe.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )
