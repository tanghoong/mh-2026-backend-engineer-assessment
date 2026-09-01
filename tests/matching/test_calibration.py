"""P3-5 — the published confidence has to mean something.

The most valuable test here is the staleness guard: a committed constant that drifts away
from what the code actually does is worse than no constant, because it is quoted with the
authority of a measurement. This is `_work/TESTING.md` tier T-D applied to a number in the
source rather than to a number in a document.
"""
from __future__ import annotations

import collections

import pytest

from src.eval import harness
from src.eval.metrics import BREAK_EVEN_P
from src.matching import calibration as C


@pytest.fixture(scope="module")
def outcomes():
    return harness.run(harness.build("pipeline"), harness.load("order_lines_train.csv"))


def test_the_committed_table_matches_a_fresh_measurement():
    """The staleness guard. Change the matcher without re-running
    `python3 -m src.matching.calibration --write` and this fails, rather than the
    submission quoting a confidence the matcher no longer earns."""
    assert C._measure() == C.CALIBRATION, (
        "calibration is stale; re-run: python3 -m src.matching.calibration --write")


def test_confidence_is_never_certain_and_never_impossible():
    """76 for 76 is not proof that error is impossible. Laplace keeps the published number
    off both endpoints, which is what a sample of 76 can actually support."""
    for reason, (_pool, conf, correct, n, _lo) in C.CALIBRATION.items():
        assert 0.0 < conf < 1.0, reason
        if correct == n:
            assert conf < 1.0, f"{reason} publishes certainty from {n} observations"


def test_confidence_tracks_the_lane_it_describes(outcomes):
    """Comparable across lanes means one thing: it estimates P(correct). Checked against
    what each lane actually did, not against the table it was generated from."""
    per_pool = collections.defaultdict(lambda: [0, 0])
    for o in outcomes:
        if o.decision.decision != "auto":
            continue
        pool = C.CALIBRATION[o.decision.reason_code][0]
        per_pool[pool][0 if o.tp else 1] += 1
    for pool, (correct, wrong) in per_pool.items():
        published = next(v[1] for v in C.CALIBRATION.values() if v[0] == pool)
        observed = correct / (correct + wrong)
        assert abs(published - observed) < 0.05, f"{pool}: says {published}, does {observed}"


def test_an_answering_lane_that_is_not_calibrated_is_a_build_failure():
    """A new lane must not silently inherit a neighbour's confidence. `_measure` raises if
    a lane answers without belonging to a pool."""
    original = dict(C.POOLS)
    try:
        C.POOLS.pop("lexical_separated")
        with pytest.raises(SystemExit, match="not in any pool"):
            C._measure()
    finally:
        C.POOLS.clear()
        C.POOLS.update(original)


def test_the_uncalibrated_default_cannot_be_mistaken_for_a_lane_that_pays():
    """An unmeasured lane should look unattractive, not neutral."""
    assert C.confidence_for("some_lane_added_next_week") == C.UNCALIBRATED
    assert C.UNCALIBRATED < BREAK_EVEN_P


def test_pools_group_lanes_that_share_a_mechanism_not_lanes_that_share_a_score():
    """alias_exact, barcode_unique and the supersession redirect all mean 'an exact
    identifier, checked for uniqueness and normalised through supersession'. Estimating
    each from a dozen observations would publish sampling error as signal."""
    assert set(C.POOLS["exact_identifier"]) == {
        "alias_exact", "alias_exact_superseded_redirect", "barcode_unique"}
    assert C.CALIBRATION["barcode_unique"][3] == C.CALIBRATION["alias_exact"][3] == 76


def test_the_lexical_interval_straddles_break_even_and_says_so():
    """Not a failure - a fact about 420 labelled lines that has to stay visible. The lane
    measures 97.7% and its one-sided 95% lower bound is 90.2%, so at this sample size it
    cannot be *proved* to pay. Reported in EVAL.md rather than rounded away."""
    _pool, conf, correct, n, lower = C.CALIBRATION["lexical_unique"]
    assert conf > BREAK_EVEN_P            # the estimate says ship
    assert lower < BREAK_EVEN_P           # the interval says we cannot prove it
    assert n < 100                        # and this is why
    exact = C.CALIBRATION["alias_exact"]
    assert exact[4] > BREAK_EVEN_P, "the identifier pool, by contrast, IS provable"
