"""The scorer has to be right before anything it scores can be trusted.

A wrong harness is worse than no harness: it produces confident numbers that steer every
later decision. These tests fix the metric definitions against hand-computed cases so a
later refactor cannot quietly change what "precision" means.
"""
from __future__ import annotations

import pytest

from src.contracts import AUTO, REJECT, Candidate, Decision
from src.eval import metrics as M


def outcome(gt: str, answered: str | None, conf: float = 0.9,
            cands: list[str] | None = None, tenant: str = "acme") -> M.Outcome:
    d = Decision(line_id="L", item_code=answered, confidence=conf,
                 decision=AUTO if answered else REJECT,
                 reason_code="x",
                 candidates=[Candidate(c, 0.9) for c in (cands or [])])
    return M.Outcome(line_id="L", tenant=tenant, segment="plain", channel="whatsapp",
                     gt=gt, decision=d)


def test_break_even_precision_is_derived_not_configured():
    """92.68% falls out of the cost table; it is not a tuned constant."""
    assert M.BREAK_EVEN_P == pytest.approx(760 / 820, abs=1e-9)
    # answering at exactly break-even is worth the same as abstaining
    n = 100_000
    tp = round(n * M.BREAK_EVEN_P)
    assert M.net_value(tp, n - tp, 0) == pytest.approx(M.net_value(0, 0, n), rel=1e-3)


def test_one_false_positive_erases_forty_correct_answers():
    """The headline asymmetry, asserted so a cost-model edit cannot pass silently."""
    assert M.net_value(40, 1, 0) == 0.0
    assert M.net_value(0, 1, 0) == -M.COST_ABSTAIN * M.FP_RATIO


def test_auto_answering_an_unanswerable_line_is_a_false_positive():
    """29.8% of train has no correct answer; answering there is not partial credit."""
    r = M.score([outcome(gt="", answered="ACM-0001")])
    assert (r.tp, r.fp, r.coverage, r.precision) == (0, 1, 1.0, 0.0)
    assert r.net == -800.0


def test_abstaining_costs_forty_whether_or_not_an_answer_existed():
    assert M.score([outcome(gt="", answered=None)]).net == -40.0
    assert M.score([outcome(gt="ACM-0001", answered=None)]).net == -40.0


def test_accuracy_and_net_value_can_disagree_about_which_matcher_to_ship():
    """The section 6.2 claim, as an executable example rather than an assertion in prose."""
    # 10 answerable, 10 unanswerable.
    always_abstain = [outcome(gt="ACM-1", answered=None) for _ in range(10)] + \
                     [outcome(gt="", answered=None) for _ in range(10)]
    # Answers all 10 answerable lines but gets 4 of them wrong; refuses the rest.
    answers_badly = [outcome(gt="ACM-1", answered="ACM-1") for _ in range(6)] + \
                    [outcome(gt="ACM-1", answered="ACM-9") for _ in range(4)] + \
                    [outcome(gt="", answered=None) for _ in range(10)]
    a, b = M.score(always_abstain), M.score(answers_badly)
    assert b.accuracy > a.accuracy          # accuracy prefers the one that answers
    assert b.net < a.net                    # net value prefers the one that does not
    assert b.precision == 0.6 < M.BREAK_EVEN_P


def test_recall_at_3_counts_only_answerable_lines_and_only_the_top_three():
    outs = [outcome(gt="ACM-1", answered=None, cands=["ACM-9", "ACM-8", "ACM-1"]),
            outcome(gt="ACM-2", answered=None, cands=["ACM-9", "ACM-8", "ACM-7", "ACM-2"]),
            outcome(gt="", answered=None, cands=["ACM-1"])]
    r = M.score(outs)
    assert r.answerable == 2
    assert r.recall_at_3 == 0.5             # the 4th-place hit does not count
    assert r.abstain_recall_at_3 == 0.5


def test_cross_tenant_leak_is_counted_in_candidates_not_just_the_answer():
    """A leaked candidate is a leak that has not been returned yet."""
    clean = M.score([outcome(gt="", answered=None, cands=["ACM-1"], tenant="acme")])
    leaked = M.score([outcome(gt="", answered=None, cands=["NRD-1"], tenant="acme")])
    assert clean.cross_tenant == 0
    assert leaked.cross_tenant == 1


def test_refusal_precision_is_undefined_when_every_line_is_answerable():
    """Reported as '-', never as 0% or 100%: no evidence is not the same as failure."""
    assert M.score([outcome(gt="ACM-1", answered="ACM-1")]).refusal_precision is None


def test_operating_curve_does_not_resurrect_structural_refusals():
    """Lowering the score floor must not turn `not_an_item` back into an answer."""
    structural = M.Outcome(
        line_id="L2", tenant="acme", segment="non_item_marker", channel="whatsapp", gt="",
        decision=Decision(line_id="L2", item_code=None, confidence=0.0, decision=REJECT,
                          reason_code="not_an_item", candidates=[]))
    curve = M.operating_curve(
        [outcome(gt="ACM-1", answered="ACM-1", conf=0.8, cands=["ACM-1"]), structural])
    assert max(p["n_auto"] for p in curve) == 1     # never 2, at any threshold


def test_p95_latency_is_nearest_rank():
    outs = [outcome(gt="", answered=None) for _ in range(100)]
    for i, o in enumerate(outs):
        o.latency_ms = float(i + 1)                 # 1..100
    assert M.latency_summary(outs)["p95_ms"] == 95.0
