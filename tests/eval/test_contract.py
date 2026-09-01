"""Tier T-C from _work/TESTING.md: rules any matcher must obey, whatever its quality.

These pass for a matcher that abstains on everything and for one that answers well. They
fail for one that is malformed, non-deterministic, or leaks across tenants - which is the
point: quality is measured, correctness is enforced.
"""
from __future__ import annotations

import pytest

from src.contracts import AUTO, REJECT, REVIEW, Candidate, Decision, OrderLine
from src.eval import harness
from src.eval.metrics import score

MATCHERS = ["null", "naive_alias", "pipeline"]
ROWS = harness.load("order_lines_train.csv")

# The closed set. An unregistered reason_code fails T-C5 rather than appearing in a report.
KNOWN_REASON_CODES = {
    # reference matchers
    "null_matcher_abstains", "no_alias_hit",
    # pipeline: identifier lanes (P3-1)
    "alias_exact", "alias_exact_superseded_redirect", "alias_ambiguous",
    "alias_expired", "alias_no_match", "alias_unresolvable",
    "barcode_unique", "barcode_ambiguous", "barcode_no_match",
    "no_identifier", "unknown_tenant",
}


@pytest.fixture(scope="module", params=MATCHERS)
def outcomes(request):
    return request.param, harness.run(harness.build(request.param), ROWS)


# ---------------------------------------------------------------- T-C4 field domains
def test_tc4_decision_and_item_code_agree(outcomes):
    _, outs = outcomes
    for o in outs:
        d = o.decision
        assert (d.decision == AUTO) == bool(d.item_code), o.line_id
        assert d.decision in (AUTO, REVIEW, REJECT)
        assert 0.0 <= d.confidence <= 1.0


def test_tc4_contract_rejects_a_malformed_decision():
    """The dataclass enforces the schema, so a bad matcher cannot reach the scorer."""
    with pytest.raises(ValueError):
        Decision("L", "ACM-1", 0.5, REJECT, "x")          # code set while abstaining
    with pytest.raises(ValueError):
        Decision("L", None, 0.5, AUTO, "x")               # auto with no code
    with pytest.raises(ValueError):
        Decision("L", None, 1.5, REJECT, "x")             # confidence out of range
    with pytest.raises(ValueError):
        Decision("L", None, 0.5, REJECT, "")              # no reason_code
    with pytest.raises(ValueError):
        Decision("L", None, 0.5, "maybe", "x")            # unknown decision


# ---------------------------------------------------------------- T-C5 explainability
def test_tc5_every_line_carries_a_registered_reason_code(outcomes):
    name, outs = outcomes
    seen = {o.decision.reason_code for o in outs}
    assert seen <= KNOWN_REASON_CODES, f"{name} emitted unregistered codes: {seen - KNOWN_REASON_CODES}"
    assert len(outs) == len(ROWS)


# ---------------------------------------------------------------- T-C3 tenant isolation
def test_tc3_no_cross_tenant_resolution(outcomes):
    """Brief section 5.4 makes any cross-tenant answer a hard fail on the task."""
    name, outs = outcomes
    assert score(outs).cross_tenant == 0, f"{name} leaked across tenants"


def test_tc3_the_check_can_actually_fail():
    """A control that cannot fail is not a control. TR-09 refuted the trap; this proves
    the guard still detects one."""
    leaked = harness.M.Outcome(
        line_id="L", tenant="acme", segment="plain", channel="whatsapp", gt="",
        decision=Decision("L", None, 0.0, REJECT, "no_alias_hit",
                          [Candidate("NRD-0001", 0.9)]))
    assert score([leaked]).cross_tenant == 1


# ---------------------------------------------------------------- T-C2 determinism
def test_tc2_two_runs_produce_identical_decisions(outcomes):
    name, outs = outcomes
    again = harness.run(harness.build(name), ROWS)
    a = [(o.line_id, o.decision.item_code, o.decision.decision,
          o.decision.reason_code, o.decision.confidence, o.decision.top3()) for o in outs]
    b = [(o.line_id, o.decision.item_code, o.decision.decision,
          o.decision.reason_code, o.decision.confidence, o.decision.top3()) for o in again]
    assert a == b


# ---------------------------------------------------------------- T-C6 latency budget
def test_tc6_p95_latency_within_budget(outcomes):
    """Brief section 5.1: measured and reported, not assumed. Construction is excluded,
    which the brief allows for cold caches - and which is why it is stated here."""
    name, outs = outcomes
    p95 = harness.M.latency_summary(outs)["p95_ms"]
    assert p95 <= 250.0, f"{name} p95 = {p95:.1f} ms"


# ---------------------------------------------------------------- T-C8 candidate format
def test_tc8_candidates_are_ranked_and_capped_at_three_on_output(outcomes):
    _, outs = outcomes
    for o in outs:
        top = o.decision.candidates[:3]
        scores = [c.score for c in top]
        assert scores == sorted(scores, reverse=True), o.line_id
        assert len(o.decision.top3().split("|")) <= 3 or not top


# ---------------------------------------------------------------- harness self-checks
def test_harness_never_shows_the_matcher_a_label():
    """Leakage guard: a label cannot reach a matcher even if the caller passes one.

    Structural rather than conventional - `OrderLine` has no field for it, and
    `from_row` drops keys it does not know, so wiring the train CSV straight into a
    matcher still cannot leak `gt_item_code`.
    """
    assert "gt_item_code" not in OrderLine.__dataclass_fields__
    row = dict(ROWS[0]) | {"gt_item_code": "ACM-LEAK", "some_future_label": "NRD-LEAK"}
    line = OrderLine.from_row(row)
    assert "LEAK" not in repr(line)


def test_null_matcher_fixes_the_zero_point():
    """-40 s per line. Anything shipped has to beat this, and 'beats zero' is not it."""
    r = score(harness.run(harness.build("null"), ROWS))
    assert r.net == -40.0 * len(ROWS) == -16800.0
    assert r.coverage == 0.0 and r.cross_tenant == 0
