#!/usr/bin/env python3
"""The matcher. Built lane by lane, in trap order, measured after each one.

    python3 -m src.eval.harness --matcher pipeline --curve --check-determinism

Stage numbering follows `DESIGN.md` §2:

    [0] normalise      [1] tenant index      [2] identifier lanes
    [3] lexical        [4] size arbitration  [5] ANSWER NORMALISATION
    [6] arbitrate and abstain

Stage 5 is not a step at the end of the chain - it is a function every candidate passes
through, wherever it came from (`TenantIndex.resolve`). That is the whole architectural
claim: exactness earns candidate *generation*, not trust.

**Current state: stages 0, 1, 2, 3, 5, and the score/margin half of 6.** The lexical lane
now answers, gated on *separation from its runner-up* rather than on absolute score. The
size/variant discriminator (P3-3b) and the four abstain detectors (P3-4) are still to come;
they exist to recover coverage from lines the margin gate currently refuses.
"""
from __future__ import annotations

from ..contracts import AUTO, REJECT, REVIEW, Candidate, Decision, OrderLine
from .text import dice, normalise, trigrams
from .index import AliasIndex, TenantIndex, build_alias_index, build_tenant_index
from .refusals import is_not_an_item, is_out_of_domain

# Provisional, and labelled as such. These are placeholders until P3-5 replaces them with
# each lane's measured precision on train. Publishing an uncalibrated number as
# `confidence` is exactly the mistake TR-02 catches the vendor making, so it is not
# allowed to survive past calibration.
PROVISIONAL_CONFIDENCE = {
    "barcode_unique": 0.95,
    "alias_exact": 0.95,
    "alias_exact_superseded_redirect": 0.95,
    "lexical_unique": 0.90,
}

# P3-3 arbitration, chosen from a 2-D sweep of the already-generated candidates rather
# than tuned by trial. The sweep is in PERF-style form in EVAL.md; the shape of it is the
# finding:
#
#   precision   floor=0.80   0.85   0.90   0.93   0.95
#   margin 0.00     81.1%   83.1%  83.1%  83.9%  83.5%
#   margin 0.10     98.3%   98.3%  99.1%  99.1%  99.0%
#   margin 0.15    100.0%  100.0% 100.0% 100.0% 100.0%
#
# Reading down a column, the score floor moves precision ~2 points across its whole
# range. Reading across a row, the margin moves it 81% -> 100%. **The margin does the
# work; the floor is nearly inert.** That generalises D-07: the question is not "is this
# a good match?" but "is it distinguishable from its runner-up?".
#
# 0.10 rather than 0.15 because it is the net-value optimum: 0.15 buys the last 0.9 points
# of precision by refusing lines worth more than the false positive it prevents.
LEXICAL_SCORE_FLOOR = 0.90
LEXICAL_MARGIN_FLOOR = 0.10


class Pipeline:
    """Tenant-scoped, deterministic, offline."""

    name = "pipeline"

    def __init__(self) -> None:
        self.tenants: dict[str, TenantIndex] = {t: build_tenant_index(t)
                                                for t in ("acme", "nordic")}
        self.alias: AliasIndex = build_alias_index()

    # ------------------------------------------------------------------ entry point
    def match(self, line: OrderLine) -> Decision:
        idx = self.tenants.get(line.tenant)
        if idx is None:
            # A tenant we have no catalogue for cannot be answered, and must not fall
            # through to another tenant's index. Cold start, hardest case.
            return self._abstain(line, "unknown_tenant")

        for lane in (self._barcode_lane, self._alias_lane):
            decision = lane(line, idx)
            if decision is not None:
                return decision
        return self._lexical_lane(line, idx)

    # ------------------------------------------------------------------ [2] barcode
    def _barcode_lane(self, line: OrderLine, idx: TenantIndex) -> Decision | None:
        """TR-06. Decisive only when the lookup yields exactly one active item.

        `barcode_hit` is the most convincing reason code available and therefore the one
        most likely to ship ungated. 8 barcodes in each tenant map to more than one
        active item, so "a barcode matched" is not the same as "the item is identified".
        """
        raw = line.raw_barcode.strip()
        if not raw:
            return None
        codes = idx.by_barcode.get(raw, [])
        resolved = self._resolve_all(codes, idx)
        if len(resolved) == 1:
            return self._answer(line, resolved[0], "barcode_unique", "barcode")
        if len(resolved) > 1:
            return self._abstain(line, "barcode_ambiguous",
                                 [Candidate(c, 0.5, "barcode") for c in resolved])
        return self._abstain(line, "barcode_no_match")

    # ------------------------------------------------------------------ [2] alias
    def _alias_lane(self, line: OrderLine, idx: TenantIndex) -> Decision | None:
        """TR-01 / TR-02 / TR-07 / TR-08.

        The lane the whole design turns on. Measured naively it is **35.9% precise** -
        worse than not having the alias table at all - and every failure has the same
        mechanism: the alias points at a superseded code. `confidence` is loaded as
        evidence and never used to gate.
        """
        sku = line.buyer_sku.strip()
        if not sku:
            return None

        valid, expired = self.alias.lookup(line.tenant, line.customer_id, sku,
                                           line.order_date)
        if not valid:
            reason = "alias_expired" if expired else "alias_no_match"
            return self._abstain(line, reason)

        # TR-07: one buyer SKU pointing at two different items is not a scoring problem,
        # it is an unanswerable question until the raw text separates them. Latent on
        # train (0 of 64 hits), so it is handled by construction rather than by evidence.
        distinct = sorted({r.item_code for r in valid})
        resolved = self._resolve_all(distinct, idx)
        if len(resolved) > 1:
            return self._abstain(line, "alias_ambiguous",
                                 [Candidate(c, 0.5, "alias") for c in resolved])
        if not resolved:
            return self._abstain(line, "alias_unresolvable")

        # TR-01: the redirect is recorded in the reason code, not hidden. An operator
        # seeing `..._superseded_redirect` knows their SKU points at a dead item.
        code = resolved[0]
        redirected = code not in distinct
        reason = "alias_exact_superseded_redirect" if redirected else "alias_exact"
        return self._answer(line, code, reason, "alias")

    # ------------------------------------------------------------------ [3] lexical
    def _lexical_lane(self, line: OrderLine, idx: TenantIndex) -> Decision:
        """P3-2. Generates candidates. Does not answer - see the module docstring.

        Scores every active item in the tenant. The catalogue is 502-1114 rows, so the
        naive scan is well inside the 250 ms budget and buys exactness: no recall is lost
        to a candidate-generation shortcut that would then have to be tuned separately.
        """
        text = normalise(line.raw_text)

        # P3-4, and the order matters. These two run AFTER the identifier lanes: if the
        # buyer gave us a SKU or a barcode they meant an item, and an explicit identifier
        # outranks a heuristic read of their prose. They run BEFORE scoring because
        # neither is a question about how close the match is - "subtotal" has no best
        # candidate, it has no question.
        if is_not_an_item(line.raw_text, text):
            return self._abstain(line, "not_an_item")
        if is_out_of_domain(text, idx.vocabulary):
            return self._abstain(line, "out_of_domain")

        query = trigrams(text)
        if not query:
            return self._abstain(line, "empty_text")

        scored = [(dice(query, tri), code) for code, tri in idx.item_trigrams.items()]
        # Sort by score descending, then by code, so ties are broken deterministically
        # rather than by dict order.
        scored.sort(key=lambda s: (-s[0], s[1]))
        top = [(sc, code) for sc, code in scored[:3] if sc > 0.0]
        if not top:
            return self._abstain(line, "no_lexical_candidate")

        cands = [Candidate(code, round(sc, 4), "lexical") for sc, code in top]
        best = cands[0]
        runner_up = cands[1].score if len(cands) > 1 else 0.0
        margin = best.score - runner_up

        if best.score < LEXICAL_SCORE_FLOOR:
            return self._abstain(line, "no_candidate_above_floor", cands)
        if margin < LEXICAL_MARGIN_FLOOR:
            # The top candidate is good but not *separable*. Answering here is the
            # twin-item false positive: a confident-looking pick between near-identical
            # rows the query did not say enough to choose between.
            return self._abstain(line, "ambiguous_candidates", cands)
        return self._answer(line, best.item_code, "lexical_unique", "lexical", cands)

    # ------------------------------------------------------------------ [5] + helpers
    def _resolve_all(self, codes: list[str], idx: TenantIndex) -> list[str]:
        """Stage 5. Every candidate from every lane passes through here."""
        out: list[str] = []
        for code in codes:
            resolved, _note = idx.resolve(code)
            if resolved and resolved not in out:
                out.append(resolved)
        return sorted(out)

    def _answer(self, line: OrderLine, code: str, reason: str, lane: str,
                candidates: list[Candidate] | None = None) -> Decision:
        conf = PROVISIONAL_CONFIDENCE[reason]
        return Decision(line_id=line.line_id, item_code=code, confidence=conf,
                        decision=AUTO, reason_code=reason,
                        candidates=candidates or [Candidate(code, conf, lane)])

    def _abstain(self, line: OrderLine, reason: str,
                 candidates: list[Candidate] | None = None) -> Decision:
        cands = candidates or []
        # `review` when we have something for a human to look at, `reject` when we do not.
        # The distinction is for the operator, not for the score.
        return Decision(line_id=line.line_id, item_code=None,
                        confidence=max((c.score for c in cands), default=0.0),
                        decision=REVIEW if cands else REJECT,
                        reason_code=reason, candidates=cands)
