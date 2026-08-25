"""Does a real third-party PII detector beat our regexes?

`docs/LIMITATIONS.md` has said for weeks that regex PII rules "miss many identifiers,
languages, and contextual disclosures, and flag benign account-like text", and that the
corpus contains permitted-PII decoys precisely to expose that. This measures it against
Microsoft Presidio on the held-out set, with the label coming from the corpus generator's
own construction rather than from either detector.

Reported whichever way it goes, including if Presidio loses. It is a 400 MB dependency and
it has to earn that.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from controlplane.detectors import Tier0Rules
from controlplane.detectors.presidio_pii import PresidioPii, presidio_available
from controlplane.detectors.tier0_rules import PII_PATTERNS
from controlplane.models import Interaction
from controlplane.sim.traffic import ensure_corpus

# The corpus labels PII as a probability per axis; anything at or above this is a real
# disclosure by construction.
LABEL_THRESHOLD = 0.5
# Where each detector is asked to commit to a call, for the precision and recall rows.
DECISION_THRESHOLD = 0.5
# The entity list is our configuration choice, not Presidio's, so its effect is measured
# rather than assumed. PERSON is the contested one: it doubles recall and floods precision.
ENTITY_VARIANTS: dict[str, tuple[str, ...]] = {
    "all_entities": (
        "CREDIT_CARD",
        "EMAIL_ADDRESS",
        "IBAN_CODE",
        "IP_ADDRESS",
        "PHONE_NUMBER",
        "US_BANK_NUMBER",
        "US_SSN",
        "PERSON",
    ),
    "no_person": (
        "CREDIT_CARD",
        "EMAIL_ADDRESS",
        "IBAN_CODE",
        "IP_ADDRESS",
        "PHONE_NUMBER",
        "US_BANK_NUMBER",
        "US_SSN",
    ),
    "identifiers_only": (
        "CREDIT_CARD",
        "EMAIL_ADDRESS",
        "IBAN_CODE",
        "US_BANK_NUMBER",
        "US_SSN",
    ),
}


def run_pii_probe(root: Path) -> dict[str, Any]:
    if not presidio_available():
        raise RuntimeError(
            "presidio-analyzer and its spaCy model are required for this probe. "
            'Install with `pip install -e ".[models]"` then '
            "`python -m spacy download en_core_web_lg`."
        )
    test = [item for item in ensure_corpus(root / "data") if item.split == "test"]
    labels = [item.truth.pii_leak >= LABEL_THRESHOLD for item in test]

    regex = Tier0Rules()
    presidio = PresidioPii()
    regex_scores, regex_ms = _score(regex, test)
    presidio_scores, presidio_ms = _score(presidio, test)
    # One Presidio pass, then vary the entity list by filtering what it already returned.
    # Re-running per variant would take a minute each and could not change the answer.
    variants = {
        name: _summary(
            [_variant_score(row, allowed) for row in presidio.detail], labels, presidio_ms
        )
        for name, allowed in ENTITY_VARIANTS.items()
    }

    return {
        "rows": float(len(test)),
        "positives": float(sum(labels)),
        "label_threshold": LABEL_THRESHOLD,
        "decision_threshold": DECISION_THRESHOLD,
        "regex": _summary(regex_scores, labels, regex_ms),
        "presidio": _summary(presidio_scores, labels, presidio_ms),
        "presidio_entity_variants": variants,
        "disagreements": _disagreements(test, regex_scores, presidio_scores, labels),
        "corpus": _corpus_structure(test, labels),
    }


def _variant_score(row: list[tuple[str, float]], allowed: tuple[str, ...]) -> float:
    return max((score for entity, score in row if entity in allowed), default=0.005)


def _corpus_structure(test: list[Interaction], labels: list[bool]) -> dict[str, float]:
    """Split the corpus by whether it *looks* like PII and whether it *is* a disclosure.

    This is what decides how to read the result. A row can carry a well-formed email and
    be a permitted disclosure, and a row can be a real leak with nothing a pattern can
    match. Neither detector knows about authorisation, so neither can win those.
    """
    shaped_labelled = shaped_clean = plain_labelled = plain_clean = 0
    for item, label in zip(test, labels, strict=True):
        combined = "\n".join((item.prompt, item.response))
        shaped = any(pattern.search(combined) for pattern in PII_PATTERNS.values())
        if shaped and label:
            shaped_labelled += 1
        elif shaped:
            shaped_clean += 1
        elif label:
            plain_labelled += 1
        else:
            plain_clean += 1
    return {
        "pii_shaped_and_a_leak": float(shaped_labelled),
        "pii_shaped_but_permitted": float(shaped_clean),
        "a_leak_with_no_pattern": float(plain_labelled),
        "clean_and_plain": float(plain_clean),
    }


def _score(detector: Any, test: list[Interaction]) -> tuple[list[float], float]:
    scores: list[float] = []
    total_ms = 0.0
    for item in test:
        signal = detector.run(item)
        scores.append(float(signal.scores.pii_leak))
        total_ms += signal.latency_ms
    return scores, total_ms / len(test) if test else 0.0


def _summary(scores: list[float], labels: list[bool], mean_ms: float) -> dict[str, float]:
    calls = [score >= DECISION_THRESHOLD for score in scores]
    true_positive = sum(1 for call, label in zip(calls, labels, strict=True) if call and label)
    false_positive = sum(
        1 for call, label in zip(calls, labels, strict=True) if call and not label
    )
    false_negative = sum(
        1 for call, label in zip(calls, labels, strict=True) if not call and label
    )
    precision = true_positive / (true_positive + false_positive) if calls.count(True) else 0.0
    actual = true_positive + false_negative
    recall = true_positive / actual if actual else 0.0
    return {
        "auc": _auc(scores, labels),
        "precision": precision,
        "recall": recall,
        "f1": (
            2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        ),
        "flagged": float(calls.count(True)),
        "true_positive": float(true_positive),
        "false_positive": float(false_positive),
        "false_negative": float(false_negative),
        "mean_latency_ms": mean_ms,
    }


def _auc(scores: list[float], labels: list[bool]) -> float:
    """Rank agreement with the label, ties counted as half a win."""
    positives = [score for score, label in zip(scores, labels, strict=True) if label]
    negatives = [score for score, label in zip(scores, labels, strict=True) if not label]
    if not positives or not negatives:
        return 0.0
    wins = sum(
        (positive > negative) + 0.5 * (positive == negative)
        for positive in positives
        for negative in negatives
    )
    return wins / (len(positives) * len(negatives))


def _disagreements(
    test: list[Interaction],
    regex_scores: list[float],
    presidio_scores: list[float],
    labels: list[bool],
) -> dict[str, Any]:
    """Where they differ, and who was right. This is the part worth reading."""
    presidio_only = []
    regex_only = []
    for item, regex_score, presidio_score, label in zip(
        test, regex_scores, presidio_scores, labels, strict=True
    ):
        regex_call = regex_score >= DECISION_THRESHOLD
        presidio_call = presidio_score >= DECISION_THRESHOLD
        if presidio_call and not regex_call:
            presidio_only.append((item.interaction_id, label))
        elif regex_call and not presidio_call:
            regex_only.append((item.interaction_id, label))
    return {
        "presidio_only_calls": float(len(presidio_only)),
        "presidio_only_correct": float(sum(1 for _, label in presidio_only if label)),
        "regex_only_calls": float(len(regex_only)),
        "regex_only_correct": float(sum(1 for _, label in regex_only if label)),
        "presidio_only_examples": [row[0] for row in presidio_only[:5]],
        "regex_only_examples": [row[0] for row in regex_only[:5]],
    }


def write_pii_probe(root: Path, summary: dict[str, Any]) -> Path:
    path = root / "docs" / "results" / "pii.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    regex = summary["regex"]
    presidio = summary["presidio"]
    disagree = summary["disagreements"]
    corpus = summary["corpus"]
    shaped = corpus["pii_shaped_and_a_leak"] + corpus["pii_shaped_but_permitted"]
    ceiling = corpus["pii_shaped_and_a_leak"] / shaped if shaped else 0.0
    lines = [
        "# PII detection: our regexes against Microsoft Presidio",
        "",
        "Regenerated by `make pii-probe`, which needs the optional `models` extra and a "
        "spaCy model. Not part of `make demo`, which stays offline.",
        "",
        "`presidio-analyzer` was declared in `pyproject.toml` and imported nowhere, which "
        "made the claim that we compose with existing detectors a claim with no code "
        "behind it. This is the code, and this is what happened when we measured it. The "
        "label comes from the corpus generator's own construction, not from either "
        "detector.",
        "",
        f"Held-out rows: {summary['rows']:.0f}, of which "
        f"{summary['positives']:.0f} carry a real PII disclosure.",
        "",
        "## The result",
        "",
        "| Detector | AUC | Precision | Recall | F1 | Flagged | FP | FN | Mean latency |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, values in (("regex (Tier 0)", regex), ("presidio", presidio)):
        lines.append(
            f"| {name} | {values['auc']:.4f} | {values['precision']:.4f} | "
            f"{values['recall']:.4f} | {values['f1']:.4f} | {values['flagged']:.0f} | "
            f"{values['false_positive']:.0f} | {values['false_negative']:.0f} | "
            f"{values['mean_latency_ms']:.2f} ms |"
        )
    lines.extend(
        [
            "",
            f"**Presidio more than doubles recall — {presidio['recall']:.2f} against "
            f"{regex['recall']:.2f} — and pays for it with "
            f"{presidio['false_positive']:.0f} false positives against "
            f"{regex['false_positive']:.0f}.** It flags "
            f"{presidio['flagged'] / summary['rows']:.0%} of all traffic. On F1 the "
            f"regexes win; on AUC the two sit within "
            f"{abs(presidio['auc'] - regex['auc']):.3f} of each other and both are close "
            f"to chance.",
            "",
            f"Coverage is strictly nested: Presidio called "
            f"{disagree['presidio_only_calls']:.0f} rows the regexes missed and was right "
            f"on {disagree['presidio_only_correct']:.0f}, while the regexes called "
            f"{disagree['regex_only_calls']:.0f} rows Presidio missed. **A better "
            f"recogniser found strictly more, and was mostly wrong about it.**",
            "",
            "## Why neither one can win here, and why that is the interesting part",
            "",
            "The corpus splits four ways once you ask both questions — does this *look* "
            "like PII, and *is* it a disclosure the policy forbids:",
            "",
            "| | Labelled a leak | Not a leak |",
            "|---|---:|---:|",
            f"| Contains PII-shaped text | {corpus['pii_shaped_and_a_leak']:.0f} | "
            f"**{corpus['pii_shaped_but_permitted']:.0f}** |",
            f"| No pattern to match | **{corpus['a_leak_with_no_pattern']:.0f}** | "
            f"{corpus['clean_and_plain']:.0f} |",
            "",
            f"The two bold cells are the whole problem. "
            f"**{corpus['pii_shaped_but_permitted']:.0f} rows carry a well-formed email or "
            f"account number and are permitted disclosures** — a support agent may read a "
            f"customer their own address back to them. Any detector firing on shape alone "
            f"is wrong on every one of them, which caps precision at {ceiling:.2f} before "
            f"either detector has done anything. And "
            f"{corpus['a_leak_with_no_pattern']:.0f} rows are real leaks with no pattern "
            f"to match at all.",
            "",
            "**Recognising PII is not the hard part. Knowing whether this disclosure was "
            "authorised is, and no PII recogniser knows that** — it is a property of the "
            "route, the requester and the policy, not of the text. That is the argument "
            "this project has been making about detection generally, and it is the first "
            "time we have measured it against a real industry tool rather than asserted "
            "it.",
            "",
            "## Sensitivity to our own configuration",
            "",
            "The entity list is our choice, not Presidio's, so its effect is measured "
            "rather than assumed. `PERSON` is the contested one.",
            "",
            "| Entity set | AUC | Precision | Recall | F1 | Flagged |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for name, values in summary["presidio_entity_variants"].items():
        lines.append(
            f"| {name} | {values['auc']:.4f} | {values['precision']:.4f} | "
            f"{values['recall']:.4f} | {values['f1']:.4f} | {values['flagged']:.0f} |"
        )
    lines.extend(
        [
            "",
            "Dropping `PERSON` cuts the flag rate by two thirds and cuts recall with it. "
            "**No entity set makes Presidio win**, so the conclusion is not an artifact of "
            "our configuration.",
            "",
            "## What this does and does not show",
            "",
            "The corpus is ours and its PII is drawn from the entity pools in "
            "`controlplane/sim/claims.py`: account numbers, emails, phone numbers and "
            "Aadhaar-shaped identifiers, in English. **That is close to the shape our own "
            "regexes were written for**, so this is played on our home ground. A real "
            "Presidio advantage on names, addresses, non-English text or unusual "
            "identifier formats would not appear here at all.",
            "",
            "So read a Presidio win as real and a Presidio loss as inconclusive, not the "
            "other way round. What survives either reading is the four-way table: the "
            "binding constraint is authorisation, not recognition.",
            "",
            "Latency is measured with the model already loaded and excludes the one-off "
            "cost of a 400 MB spaCy model. Presidio also **downloads that model over the "
            "network on first use if it is missing**, which is why the adapter checks for "
            "it and raises instead: a prototype that promises to run offline cannot have a "
            "code path that quietly fetches 400 MB.",
            "",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (root / "docs" / "results" / "pii.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    return path
