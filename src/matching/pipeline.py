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

**Current state: stages 0, 1, 2, 5 only.** Lines with no identifier abstain with
`no_identifier` rather than guessing. Coverage is therefore capped at the ~18% of lines
that carry one, and that is the point of measuring here before building further.
"""
from __future__ import annotations

from ..contracts import AUTO, REJECT, REVIEW, Candidate, Decision, OrderLine
from .index import AliasIndex, TenantIndex, build_alias_index, build_tenant_index

# Provisional, and labelled as such. These are placeholders until P3-5 replaces them with
# each lane's measured precision on train. Publishing an uncalibrated number as
# `confidence` is exactly the mistake TR-02 catches the vendor making, so it is not
# allowed to survive past calibration.
PROVISIONAL_CONFIDENCE = {
    "barcode_unique": 0.95,
    "alias_exact": 0.95,
    "alias_exact_superseded_redirect": 0.95,
}


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
        return self._abstain(line, "no_identifier")

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

    # ------------------------------------------------------------------ [5] + helpers
    def _resolve_all(self, codes: list[str], idx: TenantIndex) -> list[str]:
        """Stage 5. Every candidate from every lane passes through here."""
        out: list[str] = []
        for code in codes:
            resolved, _note = idx.resolve(code)
            if resolved and resolved not in out:
                out.append(resolved)
        return sorted(out)

    def _answer(self, line: OrderLine, code: str, reason: str, lane: str) -> Decision:
        conf = PROVISIONAL_CONFIDENCE[reason]
        return Decision(line_id=line.line_id, item_code=code, confidence=conf,
                        decision=AUTO, reason_code=reason,
                        candidates=[Candidate(code, conf, lane)])

    def _abstain(self, line: OrderLine, reason: str,
                 candidates: list[Candidate] | None = None) -> Decision:
        cands = candidates or []
        # `review` when we have something for a human to look at, `reject` when we do not.
        # The distinction is for the operator, not for the score.
        return Decision(line_id=line.line_id, item_code=None,
                        confidence=max((c.score for c in cands), default=0.0),
                        decision=REVIEW if cands else REJECT,
                        reason_code=reason, candidates=cands)
