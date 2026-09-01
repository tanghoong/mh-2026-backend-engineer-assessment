"""P3-7 — a brand-new tenant has a catalogue and zero alias history (brief 5.1).

The requirement has two halves and both are tested: it must **still work**, and its
behaviour must be **different** from a mature tenant's. A system that behaves identically
on day one and day four hundred is not cold-start safe, it is just not using its history.

Simulated by emptying the alias index rather than by a flag, so the difference is
structural - the alias lane has nothing to say, exactly as on day one of a real onboarding.

    python3 -m src.eval.harness --matcher pipeline --cold-start
"""
from __future__ import annotations

import collections

import pytest

from src.contracts import AUTO, OrderLine
from src.eval import harness
from src.eval.metrics import score
from src.matching.index import known_tenants
from src.matching.pipeline import Pipeline

ROWS = harness.load("order_lines_train.csv")


@pytest.fixture(scope="module")
def mature():
    return harness.run(harness.build("pipeline"), ROWS)


@pytest.fixture(scope="module")
def cold():
    return harness.run(harness.build_cold("pipeline"), ROWS)


def test_a_brand_new_tenant_still_works(cold):
    """Half one of the requirement. Not 'degrades gracefully' - answers, correctly."""
    r = score(cold)
    assert r.tp > 0, "a tenant with a catalogue and no history answered nothing"
    assert r.coverage > 0.10
    assert r.net > -40.0 * len(cold), "worse than abstaining on everything"


def test_it_stays_careful_rather_than_getting_lucky(mature, cold):
    """Half two, the direction that matters. Losing the alias lane must cost *coverage*,
    not precision - a cold tenant guessing to keep its numbers up would be the failure."""
    m, c = score(mature), score(cold)
    assert c.coverage < m.coverage * 0.75, "cold behaviour is not visibly different"
    assert c.fp <= m.fp, "the new tenant is taking risks the mature one does not"
    assert c.precision > 0.95


def test_the_difference_is_the_alias_lane_and_nothing_else(mature, cold):
    """Names *how* it differs, so the answer to section 5.1 is a measurement rather than a
    claim: the alias reason codes disappear and their lines land in the text lanes."""
    m = collections.Counter(o.decision.reason_code for o in mature)
    c = collections.Counter(o.decision.reason_code for o in cold)
    for alias_reason in ("alias_exact", "alias_exact_superseded_redirect"):
        assert m[alias_reason] > 0 and c[alias_reason] == 0
    # the certain refusals are catalogue-only, so they must be untouched
    for structural in ("not_an_item", "out_of_domain", "barcode_unique"):
        assert m[structural] == c[structural], structural


def test_losing_the_alias_lane_does_not_kill_the_lines_it_used_to_serve(mature, cold):
    """The fall-through fix, measured end to end. Before it, a buyer SKU the empty map did
    not recognise stopped the line dead; 64 of 420 lines, every one answerable, never had
    their text looked at. `lexical_unique` rising is the proof it is fixed."""
    m = collections.Counter(o.decision.reason_code for o in mature)
    c = collections.Counter(o.decision.reason_code for o in cold)
    assert c["lexical_unique"] > m["lexical_unique"]
    assert c["alias_no_match"] == 0, "the dead-end reason code should no longer exist"


def test_a_tenant_with_no_catalogue_is_refused_not_guessed(mature):
    """The other cold case: not 'new', but unknown. It must not fall through to some other
    tenant's index, which would be a cross-tenant answer (brief 5.4, a hard fail)."""
    pipe = Pipeline()
    d = pipe.match(OrderLine(line_id="X", tenant="tenant-we-have-never-seen",
                             customer_id="C", channel="whatsapp", order_date="2026-07-01",
                             raw_text="Kanto Hex Bolt M8x75 Stainless 304",
                             buyer_sku="004784961"))
    assert d.decision != AUTO and d.reason_code == "unknown_tenant"
    assert not d.candidates


def test_onboarding_a_tenant_is_dropping_in_a_catalogue():
    """Discovered from disk, not hardcoded. If this list had to be edited by hand, 'a
    brand-new tenant works' would depend on someone remembering to do it."""
    assert known_tenants() == ["acme", "nordic"]
    assert set(Pipeline().tenants) == set(known_tenants())
    assert set(Pipeline(tenants=["nordic"]).tenants) == {"nordic"}
