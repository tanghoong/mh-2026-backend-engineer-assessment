"""Tier T-A from _work/TESTING.md: one test per confirmed trap, on the matcher.

Same discipline as `tests/sync/`: each test is named for the single trap it isolates and
must fail for that reason alone. A test that goes green because a different defence was
added is a broken test.

Some fixtures are **synthetic**, and that is stated in each case. TR-07 in particular is
latent on this data - every ambiguous alias key is resolved by the expiry filter before
ambiguity is ever reached - so the only way to test the defence is to construct the case.
A defence that is only exercised by data we happen to have is not a defence.
"""
from __future__ import annotations

import pytest

from src.contracts import AUTO, OrderLine
from src.eval import harness
from src.matching.index import AliasRow, build_tenant_index
from src.matching.pipeline import Pipeline

ROWS = harness.load("order_lines_train.csv")


@pytest.fixture(scope="module")
def pipe() -> Pipeline:
    return Pipeline()


@pytest.fixture(scope="module")
def outcomes(pipe):
    return harness.run(pipe, ROWS)


def line(**kw) -> OrderLine:
    base = dict(line_id="X-1", tenant="acme", customer_id="CUST-001",
                channel="whatsapp", order_date="2026-07-01", raw_text="")
    return OrderLine(**(base | kw))


# ------------------------------------------------------------------ T-A1 (TR-05)
def test_ta1_a_non_item_is_never_returned_as_an_answer(pipe, outcomes):
    """Non-item rows are excluded at index build, so no lane can reach one."""
    non_items = set().union(*(i.non_items for i in pipe.tenants.values()))
    assert len(non_items) == 18, "the non-item set changed; re-check the exclusion list"
    answered = {o.decision.item_code for o in outcomes if o.decision.item_code}
    assert not (answered & non_items)
    # ...and the choke point refuses one directly, not just by luck of what was indexed.
    code = sorted(pipe.tenants["acme"].non_items)[0]
    assert pipe.tenants["acme"].resolve(code) == (None, "not_an_item")


# ------------------------------------------------------------------ T-A2 (TR-06)
def test_ta2_a_colliding_barcode_abstains_instead_of_picking_one(pipe):
    """8 barcodes per tenant map to more than one active item. `barcode_hit` is the most
    convincing reason code available, which is why it is the one most likely to ship
    ungated."""
    idx = pipe.tenants["acme"]
    colliding = next(bc for bc, codes in sorted(idx.by_barcode.items()) if len(codes) > 1)
    d = pipe.match(line(raw_barcode=colliding))
    assert d.decision != AUTO
    assert d.reason_code == "barcode_ambiguous"
    assert len(d.candidates) > 1, "the operator still needs to see both options"


def test_ta2_a_unique_barcode_still_answers(pipe):
    """The guard must not be a blanket refusal: uniqueness is the condition, not caution."""
    idx = pipe.tenants["acme"]
    unique = next(bc for bc, codes in sorted(idx.by_barcode.items()) if len(codes) == 1)
    d = pipe.match(line(raw_barcode=unique))
    assert d.decision == AUTO and d.reason_code == "barcode_unique"


# ------------------------------------------------------------------ T-A3 (TR-01)
def test_ta3_alias_to_a_superseded_code_redirects_to_its_successor(outcomes):
    """The trap the whole design turns on. Measured naively, this lane is 35.9% precise
    and all 41 failures share one mechanism."""
    by_id = {o.line_id: o for o in outcomes}
    assert by_id["ACM-T-0010"].decision.item_code == "ACM-GIWI0811"     # not ...-OLD
    assert by_id["ACM-T-0011"].decision.item_code == "ACM-ANGL0886"
    redirects = [o for o in outcomes
                 if o.decision.reason_code == "alias_exact_superseded_redirect"]
    assert len(redirects) == 41, "TR-01 measured exactly 41 poisoned alias hits on train"
    assert all(o.tp for o in redirects), "every redirect must land on the labelled answer"


def test_ta3_no_answer_anywhere_points_at_a_disabled_item(pipe, outcomes):
    """The stronger form: not one line, the whole output set."""
    for o in outcomes:
        for code in [o.decision.item_code] + [c.item_code for c in o.decision.candidates]:
            if code:
                assert not pipe.tenants[o.tenant].items[code].disabled, o.line_id


def test_ta3_a_superseded_code_with_no_successor_abstains(pipe):
    """Redirect only where an active successor exists. A discontinued item must not be
    silently replaced - that would ship the wrong goods with high confidence."""
    idx = pipe.tenants["acme"]
    idx.superseded.pop("ACM-ANGL0886-OLD")
    idx.orphan_disabled.add("ACM-ANGL0886-OLD")
    try:
        assert idx.resolve("ACM-ANGL0886-OLD") == (None, "superseded_no_successor")
    finally:
        idx.orphan_disabled.discard("ACM-ANGL0886-OLD")
        idx.superseded["ACM-ANGL0886-OLD"] = "ACM-ANGL0886"


# ------------------------------------------------------------------ T-A4 (TR-02)
def test_ta4_a_low_vendor_confidence_alias_is_still_answered(outcomes):
    """`confidence` is anti-informative here: 22.6% precision at 1.0, 100% at 0.55. A
    `>= 0.9` floor would select exactly the 41 poisoned rows and discard 11 correct ones.
    ACM-T-0008's only alias row carries confidence 0.55 and is correct."""
    d = {o.line_id: o for o in outcomes}["ACM-T-0008"]
    assert d.decision.decision == AUTO
    assert d.decision.item_code == "ACM-BALL0123" == d.gt


def test_ta4_vendor_confidence_is_not_used_as_our_confidence(outcomes):
    """Our published confidence must be ours. If the vendor's value were passed through,
    answers would carry 0.55/0.72/1.0 - the three values the column takes."""
    published = {round(o.decision.confidence, 4)
                 for o in outcomes if o.decision.decision == AUTO}
    assert not (published & {0.55, 0.72, 1.0}), f"vendor confidence leaked out: {published}"


# ------------------------------------------------------------------ T-A5 (TR-08)
def test_ta5_an_expired_alias_row_is_not_used(pipe):
    """Synthetic: on this data every expired row shares a key with a live one, so an
    expired-only key never occurs. It is one deletion away from occurring in production."""
    key = ("acme", "CUST-001", "zz-expired")
    pipe.alias.rows[key] = [AliasRow("acme", "CUST-001", "ZZ-EXPIRED", "ACM-BALL0123",
                                     "2026-01-01", "2026-03-31", "manual_import", 1.0)]
    try:
        d = pipe.match(line(buyer_sku="ZZ-EXPIRED", order_date="2026-07-01"))
        assert d.decision != AUTO and d.reason_code == "alias_expired"
        # and the same row inside its window is used, so this is expiry and not a refusal
        d2 = pipe.match(line(buyer_sku="ZZ-EXPIRED", order_date="2026-02-01"))
        assert d2.decision == AUTO and d2.item_code == "ACM-BALL0123"
    finally:
        del pipe.alias.rows[key]


# ------------------------------------------------------------------ T-A6 (TR-07)
def test_ta6_a_genuinely_ambiguous_alias_key_abstains(pipe):
    """Synthetic, and deliberately so.

    On this data TR-07 collapses entirely into TR-08: all 26 keys with two item codes are
    exactly the 26 keys carrying an expired row, and the validity filter resolves 26/26 to
    a single code. The ambiguity branch is therefore dead code here - which is the reason
    it must be tested rather than deleted. Two open mappings is one bad import away.
    """
    key = ("acme", "CUST-001", "zz-ambig")
    pipe.alias.rows[key] = [
        AliasRow("acme", "CUST-001", "ZZ-AMBIG", "ACM-BALL0123", "2026-01-01", "",
                 "confirmed_order", 1.0),
        AliasRow("acme", "CUST-001", "ZZ-AMBIG", "ACM-HEXB1049", "2026-01-01", "",
                 "confirmed_order", 1.0),
    ]
    try:
        d = pipe.match(line(buyer_sku="ZZ-AMBIG"))
        assert d.decision != AUTO and d.reason_code == "alias_ambiguous"
        assert {c.item_code for c in d.candidates} == {"ACM-BALL0123", "ACM-HEXB1049"}
    finally:
        del pipe.alias.rows[key]


# ------------------------------------------------------------------ tenant isolation
def test_tenant_isolation_is_structural_not_a_filter(pipe):
    """Separate per-tenant indexes, so a nordic code is not reachable from an acme line
    even if a lane asked for it. TR-09 refuted the trap; the control stays (D-09)."""
    assert pipe.tenants["acme"].resolve("NRD-FULL0120") == (None, "unknown_code")
    d = pipe.match(line(tenant="zzz-new-tenant", buyer_sku="004784961"))
    assert d.decision != AUTO and d.reason_code == "unknown_tenant"
