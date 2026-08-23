from __future__ import annotations

import json

from controlplane.detectors.ollama_judge import _parse, _prompt


def test_short_axis_keys_map_onto_the_harm_vector() -> None:
    raw = json.dumps(
        {"spans": [{"i": 0, "hal": 0.0, "pii": 1.0, "bias": 0.0, "unsafe": 0.0, "inj": 0.0}]}
    )
    scores = _parse(raw, expected=1)
    assert scores[0].pii_leak == 1.0
    assert scores[0].hallucination == 0.0


def test_a_missing_span_scores_zero_rather_than_guessing() -> None:
    """A short reply must not shift later spans onto the wrong text."""
    raw = json.dumps({"spans": [{"i": 2, "pii": 1.0}]})
    scores = _parse(raw, expected=4)
    assert len(scores) == 4
    assert scores[2].pii_leak == 1.0
    assert [score.maximum() for score in (scores[0], scores[1], scores[3])] == [0.0, 0.0, 0.0]


def test_malformed_json_yields_zeros_not_an_exception() -> None:
    scores = _parse("not json at all", expected=3)
    assert len(scores) == 3
    assert all(score.maximum() == 0.0 for score in scores)


def test_unknown_or_misspelled_keys_are_ignored() -> None:
    """An early run returned injection_or_exfl on every call; unknown keys must not leak in."""
    raw = json.dumps({"spans": [{"i": 0, "injection_or_exfl": 1.0, "inj": 0.5}]})
    scores = _parse(raw, expected=1)
    assert scores[0].injection_or_exfil == 0.5


def test_out_of_range_scores_are_clamped() -> None:
    raw = json.dumps({"spans": [{"i": 0, "hal": 7.0, "pii": -3.0}]})
    scores = _parse(raw, expected=1)
    assert scores[0].hallucination == 1.0
    assert scores[0].pii_leak == 0.0


def test_non_numeric_scores_are_ignored() -> None:
    raw = json.dumps({"spans": [{"i": 0, "hal": "high", "pii": None, "bias": 1.0}]})
    scores = _parse(raw, expected=1)
    assert scores[0].hallucination == 0.0
    assert scores[0].bias == 1.0


def test_prompt_numbers_every_span_and_states_the_count() -> None:
    prompt = _prompt(["first claim.", "second claim."], "the source")
    assert "[0] first claim." in prompt
    assert "[1] second claim." in prompt
    assert "Exactly 2 entries" in prompt
    assert "the source" in prompt
