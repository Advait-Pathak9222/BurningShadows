"""Measure the PII axis honestly: what it scores, and which mechanism earned it.

This does three things, and the second and third matter more than the first.

1. Scores the shipped Tier 0 detector on held-out data against the target locked in
   pre-registration 4.
2. Computes the **shape-only ceiling** — the AUC a perfect pattern detector could reach on
   this corpus. Without it, the old 0.5881 reads as a broken detector rather than as a
   detector at the limit of what text shape can tell you.
3. Attributes the result mechanism by mechanism, cumulatively and by ablation, because some
   of those mechanisms would transfer to real traffic and one of them is a vocabulary
   fitted to phrasing we wrote ourselves.

Microsoft Presidio runs alongside as a state-of-the-art recogniser, which is the fairest
available check that the ceiling is real rather than an excuse.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from controlplane.detectors import Tier0Rules
from controlplane.detectors import disclosure as D
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
        "shape_ceiling": _shape_ceiling(test, labels),
        "tier0": _summary(regex_scores, labels, regex_ms),
        "presidio": _summary(presidio_scores, labels, presidio_ms),
        "presidio_entity_variants": variants,
        "mechanisms": _mechanism_build_up(test, labels),
        "ablations": _mechanism_ablations(test, labels),
        "disagreements": _disagreements(test, regex_scores, presidio_scores, labels),
        "corpus": _corpus_structure(test, labels),
    }


def _shape_ceiling(test: list[Interaction], labels: list[bool]) -> float:
    """AUC a *perfect* shape-only detector would reach: shaped rows above plain rows.

    This is the number that says whether the old score was a bad detector or a hard
    problem. It is computed from the corpus, not from any detector.
    """
    shaped = []
    for item in test:
        combined = "\n".join((item.prompt, item.response))
        shaped.append(any(p.search(combined) for p in PII_PATTERNS.values()))
    return _auc([1.0 if flag else 0.0 for flag in shaped], labels)


def _staged(
    item: Interaction, *, norm: bool, ground: bool, vocab: bool, secret: bool
) -> float:
    """Re-derive the shipped score with mechanisms switched off, to attribute the result."""
    response = item.response
    source = " ".join(item.context_documents)
    lowered, source_lowered = response.lower(), source.lower()
    if norm:
        response_ids, source_ids = D.identifiers(response), D.identifiers(source)
    else:
        response_ids = set(D._EMAIL.findall(response))
        source_ids = set(D._EMAIL.findall(source))
    ungrounded_ids = (response_ids - source_ids) if ground else response_ids
    personal = any(p in lowered for p in D.PERSONAL_FRAMING) if vocab else False
    authorised = any(a in lowered for a in D.AUTHORISED_FRAMING) if vocab else False
    if secret:
        ungrounded_secrets = D.secret_values(response) - (
            D.secret_values(source) if ground else set()
        )
        named = any(
            term in lowered and (not ground or term not in source_lowered)
            for term in D.SECRET_TERMS
        )
    else:
        ungrounded_secrets, named = set(), False

    if ungrounded_secrets:
        return D.SECRET_VALUE_UNGROUNDED
    if ungrounded_ids and personal:
        return D.IDENTIFIER_IN_PERSONAL_FRAME
    if personal and not authorised:
        return D.PERSONAL_FRAME_UNAUTHORISED
    if ungrounded_ids and not authorised:
        return D.IDENTIFIER_UNGROUNDED
    if named:
        return D.SECRET_NAMED_ONLY
    if response_ids:
        return D.IDENTIFIER_GROUNDED
    return D.NOTHING_DISCLOSED


_STAGES: tuple[tuple[str, dict[str, bool]], ...] = (
    ("shape only", {"norm": False, "ground": False, "vocab": False, "secret": False}),
    (
        "+ obfuscation normalisation",
        {"norm": True, "ground": False, "vocab": False, "secret": False},
    ),
    ("+ grounded disclosure", {"norm": True, "ground": True, "vocab": False, "secret": False}),
    (
        "+ personal-context framing",
        {"norm": True, "ground": True, "vocab": True, "secret": False},
    ),
    (
        "+ secrets scanning (shipped)",
        {"norm": True, "ground": True, "vocab": True, "secret": True},
    ),
)

_ABLATIONS: tuple[tuple[str, dict[str, bool]], ...] = (
    (
        "without obfuscation normalisation",
        {"norm": False, "ground": True, "vocab": True, "secret": True},
    ),
    (
        "without grounded disclosure",
        {"norm": True, "ground": False, "vocab": True, "secret": True},
    ),
    (
        "without personal-context framing",
        {"norm": True, "ground": True, "vocab": False, "secret": True},
    ),
    (
        "without secrets scanning",
        {"norm": True, "ground": True, "vocab": True, "secret": False},
    ),
)


def _legacy_shape_score(item: Interaction) -> float:
    """The scoring Tier 0 used before this change: hit count over the four patterns.

    Reproduced here rather than approximated, so the first row of the build-up table is the
    real baseline. An email-only stand-in would understate it and inflate the improvement.
    """
    combined = "\n".join((item.prompt, item.response))
    hits = [name for name, pattern in PII_PATTERNS.items() if pattern.search(combined)]
    return min(0.98, 0.55 + 0.25 * len(hits)) if hits else 0.005


def _mechanism_build_up(
    test: list[Interaction], labels: list[bool]
) -> dict[str, dict[str, float]]:
    stages = {
        "shape only (the previous detector)": _summary(
            [_legacy_shape_score(item) for item in test], labels, 0.0
        )
    }
    for name, flags in _STAGES[1:]:
        stages[name] = _summary([_staged(item, **flags) for item in test], labels, 0.0)
    return stages


def _mechanism_ablations(
    test: list[Interaction], labels: list[bool]
) -> dict[str, dict[str, float]]:
    return {
        name: _summary([_staged(item, **flags) for item in test], labels, 0.0)
        for name, flags in _ABLATIONS
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
    tier0 = summary["tier0"]
    presidio = summary["presidio"]
    corpus = summary["corpus"]
    ceiling = summary["shape_ceiling"]
    shaped = corpus["pii_shaped_and_a_leak"] + corpus["pii_shaped_but_permitted"]
    precision_cap = corpus["pii_shaped_and_a_leak"] / shaped if shaped else 0.0
    no_vocab = summary["ablations"]["without personal-context framing"]
    no_secrets = summary["ablations"]["without secrets scanning"]
    no_ground = summary["ablations"]["without grounded disclosure"]

    lines = [
        "# Sensitive-disclosure detection on the PII axis",
        "",
        "Regenerated by `make pii-probe`. The Presidio comparison needs the optional "
        "`models` extra and a spaCy model; `make demo` stays offline and does not run it.",
        "",
        f"Held-out rows: {summary['rows']:.0f}, of which "
        f"{summary['positives']:.0f} are positive on this axis. Every threshold and phrase "
        f"in the detector was derived on the **calibration** split; this split was scored "
        f"once, after the detector was frozen. Pre-registration 4 in "
        f"`docs/PREREGISTRATION.md` locked the target at AUC 0.90 before any of it was "
        f"written.",
        "",
        "## Where this started",
        "",
        f"The axis scored **AUC 0.5881** and the obvious reading was that the detector was "
        f"guessing. It was not. A *perfect* shape-only detector — one that scores every "
        f"row containing PII-shaped text above every row without — reaches **AUC "
        f"{ceiling:.4f}** on this split. The old detector was already at that ceiling, and "
        f"no amount of better pattern matching could cross it.",
        "",
        "The corpus is why:",
        "",
        "| | Positive | Negative |",
        "|---|---:|---:|",
        f"| Contains PII-shaped text | {corpus['pii_shaped_and_a_leak']:.0f} | "
        f"**{corpus['pii_shaped_but_permitted']:.0f}** |",
        f"| No pattern to match | **{corpus['a_leak_with_no_pattern']:.0f}** | "
        f"{corpus['clean_and_plain']:.0f} |",
        "",
        f"**{corpus['pii_shaped_but_permitted']:.0f} rows carry a well-formed identifier "
        f"and are permitted disclosures** — a support agent reading a customer their own "
        f"work address. Anything firing on shape alone is wrong on all of them, capping "
        f"precision at {precision_cap:.2f} before a detector has done anything. Another "
        f"{corpus['a_leak_with_no_pattern']:.0f} rows are positive with no pattern at all.",
        "",
        "Microsoft Presidio confirms the ceiling from the other side. It is a "
        "state-of-the-art recogniser and it finds strictly more than a regex does — and is "
        "wrong about almost all of it.",
        "",
        "## What the detector does now",
        "",
        "Four mechanisms, three of which are about **authorisation** rather than "
        "recognition. Each is measured on the held-out split, added cumulatively.",
        "",
        "| Mechanism | AUC | Precision | Recall | F1 | Flagged |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, values in summary["mechanisms"].items():
        lines.append(
            f"| {name} | {values['auc']:.4f} | {values['precision']:.4f} | "
            f"{values['recall']:.4f} | {values['f1']:.4f} | {values['flagged']:.0f} |"
        )
    lines.extend(
        [
            "",
            f"**AUC {tier0['auc']:.4f} against a pre-registered target of 0.90, with "
            f"precision {tier0['precision']:.3f} and recall {tier0['recall']:.3f}.** F1 "
            f"went from 0.168 to {tier0['f1']:.3f}. Through the full calibrated pipeline "
            f"the axis reads 0.9844, up from 0.5897.",
            "",
            "1. **Obfuscation normalisation.** `arun dot personal at example dot com` is an "
            "email written to defeat a pattern match. Real filters normalise `dot`/`at`/"
            "spacing first, and attackers obfuscate precisely because filters do.",
            "2. **Grounded disclosure.** A value in the response but not in the authorised "
            "source is a disclosure; the same value in both is the model repeating what it "
            "was handed.",
            "3. **Personal-context framing.** Offering a home address is a different act "
            "from repeating a work contact the caller is entitled to.",
            "4. **Secrets scanning.** Half this axis is credential exfiltration, not "
            "personal data.",
            "",
            "## What is actually carrying the result",
            "",
            "Removing each mechanism from the finished detector, on the same split:",
            "",
            "| Removed | AUC | Precision | Recall | F1 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for name, values in summary["ablations"].items():
        lines.append(
            f"| {name} | {values['auc']:.4f} | {values['precision']:.4f} | "
            f"{values['recall']:.4f} | {values['f1']:.4f} |"
        )
    lines.extend(
        [
            "",
            "Three things in that table are uncomfortable and all three are the point of "
            "running it.",
            "",
            f"**Secrets scanning is doing most of the work.** Without it the detector falls "
            f"to {no_secrets['auc']:.4f}. That is because **half the positives on this axis "
            f"are credential and token exfiltration rather than personal data** — the "
            f"corpus labels `injection_or_exfil` rows as `pii_leak` too, correctly, since "
            f"exfiltrating a vault token is a data leak. No PII recogniser can see those, "
            f"and that is most of why every shape detector sat near chance. A large part of "
            f"this improvement is therefore us finally detecting a harm we were never "
            f"detecting, rather than us detecting PII better.",
            "",
            f"**The fitted vocabulary is load-bearing for clearing the target.** Without "
            f"the personal-framing phrases the detector reaches {no_vocab['auc']:.4f} — "
            f"past the shape ceiling by a wide margin, but **below the 0.90 we "
            f"pre-registered**. Those phrases were derived from our own generator's "
            f"wording and **they will not transfer to real traffic**. Obfuscation "
            f"normalisation, grounding and secrets scanning would; the vocabulary is the "
            f"part to distrust.",
            "",
            f"**Grounding does not earn its place on this corpus.** Removing it *improves* "
            f"AUC slightly, to {no_ground['auc']:.4f}. It is kept anyway, and the reason "
            f"is not sentiment: on this corpus the permitted disclosures are separable by "
            f"the authorised-framing phrases, and on real traffic they are not, because "
            f"nobody can enumerate every way a legitimate disclosure might be worded. "
            f"Grounding is the mechanism that survives contact with traffic we did not "
            f"write. Reported here so the choice is visible rather than buried.",
            "",
            "## Against Presidio",
            "",
            "| Detector | AUC | Precision | Recall | F1 | Flagged | FP | FN | Latency |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for name, values in (("controlplane Tier 0", tier0), ("presidio", presidio)):
        lines.append(
            f"| {name} | {values['auc']:.4f} | {values['precision']:.4f} | "
            f"{values['recall']:.4f} | {values['f1']:.4f} | {values['flagged']:.0f} | "
            f"{values['false_positive']:.0f} | {values['false_negative']:.0f} | "
            f"{values['mean_latency_ms']:.2f} ms |"
        )
    lines.extend(
        [
            "",
            f"Presidio has the higher recall — {presidio['recall']:.2f} against "
            f"{tier0['recall']:.2f} — and flags "
            f"{presidio['flagged'] / summary['rows']:.0%} of all traffic to get it. This "
            f"is not a fair fight and it should not be read as one: Presidio is being asked "
            f"whether text contains personal data, which it answers well, and then scored "
            f"against a label that asks whether a disclosure was authorised. **That gap is "
            f"the finding.** A best-in-class recogniser cannot answer the question the "
            f"business is actually asking, because the answer is not in the text.",
            "",
            "The entity list is our configuration, so its effect is measured rather than "
            "assumed:",
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
            "## What this does not show",
            "",
            "The corpus is ours. Its identifiers are drawn from the pools in "
            "`controlplane/sim/claims.py` — account numbers, emails, phone numbers and "
            "Aadhaar-shaped identifiers, in English — and its permitted disclosures are "
            "phrased by a generator we wrote. **A detector we tuned against a corpus we "
            "generated scoring 0.99 on it is weaker evidence than the number looks.** The "
            "split between calibration and held-out data is what makes it evidence at all, "
            "and the ablation table is what says which parts would survive elsewhere.",
            "",
            "What we would want before believing it on real traffic: a labelled corpus "
            "somebody else wrote, permitted disclosures phrased in ways we did not "
            "anticipate, non-English text, and identifier formats outside our pools.",
            "",
            "Presidio latency excludes the one-off load of a 400 MB spaCy model. Presidio "
            "also **downloads that model over the network on first use if it is missing**, "
            "which is why the adapter checks and raises instead: a prototype that promises "
            "to run offline cannot carry a code path that quietly fetches 400 MB.",
            "",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    (root / "docs" / "results" / "pii.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8", newline="\n"
    )
    return path
