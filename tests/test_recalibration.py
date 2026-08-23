from __future__ import annotations

from controlplane.models import ReviewRecord, ReviewVerdict
from controlplane.review import audit_sample, catch_rates, intervention_precision
from controlplane.review.recalibration import MIN_OBSERVATIONS


def _record(
    index: int, *, harm: bool, withheld: bool, tier: int | None = 2
) -> ReviewRecord:
    return ReviewRecord(
        interaction_id=f"row-{index:04d}",
        route="support-assistant",
        reviewer="test",
        verdict=ReviewVerdict.UPHELD if harm == withheld else ReviewVerdict.OVERTURNED,
        reason_code="test",
        observed_harm=harm,
        system_withheld=withheld,
        selected_tier=tier,
    )


def test_catch_rate_counts_only_rows_the_tier_actually_ran_on() -> None:
    """A row nobody checked says nothing about a detector's ability to catch."""
    records = [_record(i, harm=True, withheld=True, tier=2) for i in range(12)]
    records += [_record(100 + i, harm=True, withheld=False, tier=None) for i in range(50)]
    estimate = catch_rates(records, {2: 0.88})[2]
    assert estimate.observations == 12
    assert estimate.misses == 0


def test_misses_pull_the_measured_catch_rate_down() -> None:
    caught = [_record(i, harm=True, withheld=True) for i in range(15)]
    missed = [_record(100 + i, harm=True, withheld=False) for i in range(15)]
    high = catch_rates(caught, {2: 0.88})[2]
    mixed = catch_rates(caught + missed, {2: 0.88})[2]
    assert mixed.posterior_mean < high.posterior_mean


def test_clean_rows_are_not_evidence_about_catch_rate() -> None:
    """Catch rate is conditioned on harm being present."""
    records = [_record(i, harm=False, withheld=True) for i in range(20)]
    assert catch_rates(records, {2: 0.88})[2].observations == 0


def test_an_unexercised_tier_reports_no_measurement() -> None:
    """Reporting the Beta prior as a measured rate would be inventing a number."""
    estimate = catch_rates([], {1: 0.68})[1]
    assert estimate.observations == 0
    assert estimate.has_evidence is False
    assert estimate.reportable is None


def test_evidence_threshold_is_the_gate() -> None:
    below = [_record(i, harm=True, withheld=True) for i in range(MIN_OBSERVATIONS - 1)]
    at = [_record(i, harm=True, withheld=True) for i in range(MIN_OBSERVATIONS)]
    assert catch_rates(below, {2: 0.88})[2].reportable is None
    assert catch_rates(at, {2: 0.88})[2].reportable is not None


def test_precision_measures_agreement_with_what_we_withheld() -> None:
    records = [_record(i, harm=True, withheld=True) for i in range(3)]
    records += [_record(10 + i, harm=False, withheld=True) for i in range(1)]
    summary = intervention_precision(records)
    assert summary["withheld"] == 4.0
    assert summary["precision"] == 0.75


def test_the_audit_slice_comes_from_released_rows_and_is_deterministic() -> None:
    identifiers = [f"row-{index:04d}" for index in range(2000)]
    first = audit_sample(identifiers, 0.08)
    assert first == audit_sample(identifiers, 0.08)
    assert 0.05 < len(first) / len(identifiers) < 0.11


def test_a_larger_audit_rate_samples_more() -> None:
    identifiers = [f"row-{index:04d}" for index in range(2000)]
    assert len(audit_sample(identifiers, 0.20)) > len(audit_sample(identifiers, 0.05))
