"""T-A9 — abstain is four classes, not one (TR-03).

Two of the four are *certain* refusals and are held to 100% on train. The other two are
uncertain by construction; their test is not "how often were they right to refuse" but
"did they hand the reviewer something usable", which is what makes a 40 s abstention cheap
rather than merely correct.
"""
from __future__ import annotations

import pytest

from src.eval import harness
from src.matching.index import build_tenant_index
from src.matching.refusals import DOMAIN_TOKEN_FLOOR, domain_overlap, is_not_an_item, is_out_of_domain
from src.matching.text import normalise

ROWS = harness.load("order_lines_train.csv")


@pytest.fixture(scope="module")
def outcomes():
    return harness.run(harness.build("pipeline"), ROWS)


@pytest.fixture(scope="module")
def vocab():
    return {t: build_tenant_index(t).vocabulary for t in ("acme", "nordic")}


# ---------------------------------------------------------------- the four classes exist
def test_ta9_all_four_abstain_classes_have_support(outcomes):
    """A reason code nobody ever emits is documentation, not behaviour."""
    seen = {o.decision.reason_code for o in outcomes if o.decision.decision != "auto"}
    for reason in ("not_an_item", "out_of_domain", "ambiguous_candidates",
                   "no_candidate_above_floor"):
        assert reason in seen, f"{reason} is documented but never emitted"


# ---------------------------------------------------------------- the certain two
def test_certain_refusals_never_discard_an_answerable_line(outcomes):
    """`not_an_item` and `out_of_domain` claim to *know*. Held to 100% on train, because a
    detector that is merely usually right belongs in the uncertain bucket with the others."""
    wrong = [o.line_id for o in outcomes
             if o.decision.reason_code in ("not_an_item", "out_of_domain") and o.answerable]
    assert not wrong, f"a certain refusal threw away an answerable line: {wrong}"


def test_an_explicit_identifier_outranks_a_heuristic_read_of_the_prose(outcomes):
    """If the buyer gave us a SKU or a barcode they meant an item. The detectors run after
    the identifier lanes, and this asserts that ordering rather than trusting it."""
    byid = {r["line_id"]: r for r in ROWS}
    overridden = [o.line_id for o in outcomes
                  if o.decision.reason_code in ("not_an_item", "out_of_domain")
                  and (byid[o.line_id]["buyer_sku"].strip()
                       or byid[o.line_id]["raw_barcode"].strip())]
    assert not overridden, f"a text heuristic overrode an explicit identifier: {overridden}"


@pytest.mark.parametrize("text", ["subtotal", "same as last month order",
                                  "TOTAL", "as per attached", "delivery"])
def test_bookkeeping_text_is_not_an_order_line(text):
    assert is_not_an_item(text, normalise(text))


@pytest.mark.parametrize("text", ["Cadbury Dairy Milk 165g",          # food, in hardware
                                  "Wagyu striploin MB7 grain fed",
                                  "Epson 003 ink black bottle"])
def test_another_industrys_product_is_out_of_domain_not_a_weak_match(text, vocab):
    """A real product and a real order - for somebody else. That is a different question
    from 'I am not confident', and the reviewer should be told which."""
    assert is_out_of_domain(normalise(text), vocab["acme"])


def test_a_real_tenant_item_is_not_out_of_domain(vocab):
    """The detector must be able to say no, or it is just a refusal in disguise."""
    assert not is_out_of_domain(normalise("Kanto Hex Bolt M8x75 Stainless 304"), vocab["acme"])
    assert domain_overlap(normalise("Kanto Hex Bolt M8x75"), vocab["acme"]) > DOMAIN_TOKEN_FLOOR


def test_the_domain_threshold_sits_on_a_plateau_not_a_knife_edge(outcomes, vocab):
    """Every floor from 0 to 0.34 refuses only unanswerable lines; the first mistake
    appears at 0.40. A constant tuned to the last decimal would not survive the holdout."""
    byid = {r["line_id"]: r for r in ROWS}
    refused = [o for o in outcomes if o.decision.decision != "auto"]
    for floor in (0.0, 0.10, 0.20, 0.25, DOMAIN_TOKEN_FLOOR):
        fired = [o for o in refused
                 if domain_overlap(normalise(byid[o.line_id]["raw_text"]), vocab[o.tenant]) <= floor
                 and not is_not_an_item(byid[o.line_id]["raw_text"],
                                        normalise(byid[o.line_id]["raw_text"]))]
        assert all(not o.answerable for o in fired), f"floor {floor} loses an answerable line"


# ---------------------------------------------------------------- the uncertain two
def test_an_uncertain_refusal_hands_the_reviewer_the_answer(outcomes):
    """The number that decides whether a 40 s abstention is cheap. When the system says
    'you pick', the right code is in the top 3 for ~99% of the lines that have one."""
    for reason in ("ambiguous_candidates", "no_candidate_above_floor"):
        grp = [o for o in outcomes if o.decision.reason_code == reason and o.answerable]
        hit = sum(1 for o in grp if o.gt in [c.item_code for c in o.decision.candidates[:3]])
        assert hit / len(grp) >= 0.95, f"{reason}: only {hit}/{len(grp)} carry the answer"


def test_a_certain_refusal_offers_no_candidates(outcomes):
    """Offering candidates alongside 'this is not an item' would invite the reviewer to
    pick one. The two refusal kinds must look different to a human, not just to a grep."""
    for o in outcomes:
        if o.decision.reason_code in ("not_an_item", "out_of_domain"):
            assert not o.decision.candidates, o.line_id
