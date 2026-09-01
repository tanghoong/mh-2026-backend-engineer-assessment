#!/usr/bin/env python3
"""Two reference matchers, built before the real one.

They exist so the harness can be validated against known-shaped behaviour rather than
against itself. A harness that cannot separate these two is not measuring anything.

* `NullMatcher` abstains on everything. It fixes the **zero point**: -40 s per line, or
  -16,800 s over train. Any shipped matcher has to beat this, and "beats zero" is not
  the same as "beats doing nothing".

* `NaiveAliasMatcher` is the design most people would write first: a buyer-SKU exact hit
  in `customer_sku_map.csv` is the highest-confidence evidence available, so answer it.
  TR-01 measures that lane at **35.9% precision**. Running it through the harness turns
  that probe result into a scored, per-segment, net-value number - which is the argument
  `DECISIONS.md` D-03 rests on, made in the harness's own terms rather than a script's.
"""
from __future__ import annotations

import csv
import pathlib

from ..contracts import AUTO, REJECT, Candidate, Decision, OrderLine

DATA = pathlib.Path(__file__).resolve().parents[2] / "data"


class NullMatcher:
    """Abstain on everything. The zero point, not zero."""

    name = "null"

    def match(self, line: OrderLine) -> Decision:
        return Decision(line_id=line.line_id, item_code=None, confidence=0.0,
                        decision=REJECT, reason_code="null_matcher_abstains",
                        candidates=[])


class NaiveAliasMatcher:
    """Answer any exact buyer-SKU hit; abstain otherwise.

    Deliberately reproduces the intuitive mistake in full: it trusts the alias table, it
    trusts `confidence`, it does not check `valid_to`, and it does not resolve
    supersession. Kept as a fixed reference point so later matchers are compared against
    the obvious design rather than against nothing.
    """

    name = "naive_alias"

    def __init__(self) -> None:
        self.alias: dict[tuple[str, str, str], list[dict]] = {}
        with open(DATA / "customer_sku_map.csv", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                key = (row["tenant"], row["customer_id"], row["customer_sku"].strip().lower())
                self.alias.setdefault(key, []).append(row)

    def match(self, line: OrderLine) -> Decision:
        sku = line.buyer_sku.strip().lower()
        rows = self.alias.get((line.tenant, line.customer_id, sku)) if sku else None
        if not rows:
            return Decision(line_id=line.line_id, item_code=None, confidence=0.0,
                            decision=REJECT, reason_code="no_alias_hit", candidates=[])
        # Takes the first row and the vendor's own confidence, exactly as a first
        # implementation would. Both are wrong; TR-01 and TR-02 say how wrong.
        best = rows[0]
        conf = float(best["confidence"])
        cands = [Candidate(item_code=r["item_code"], score=float(r["confidence"]),
                           lane="alias_exact", evidence=(r["source"],)) for r in rows]
        return Decision(line_id=line.line_id, item_code=best["item_code"], confidence=conf,
                        decision=AUTO, reason_code="alias_exact", candidates=cands)
