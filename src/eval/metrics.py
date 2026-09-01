#!/usr/bin/env python3
"""Metric definitions for the evaluation harness.

The cost model is `DESIGN.md` §1 and derives from the brief §1, not from taste:

    correct auto  +20 s      wrong auto  -800 s      abstain  -40 s

Two definitions carry weight and are stated here rather than left implicit:

* **A wrong auto includes auto-answering a line that has no correct answer.** 29.8% of
  train has a blank label; a matcher that ignores them is not being cautious, it is
  scoring 41 false positives.
* **An abstention costs 40 s whether or not an answer existed.** The line reaches the
  review queue either way. Refusing correctly is not free; it is merely 20x cheaper
  than being wrong.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from ..contracts import AUTO, Decision

SAVED_CORRECT = 20.0
COST_ABSTAIN = 40.0
FP_RATIO = 20.0
COST_WRONG = COST_ABSTAIN * FP_RATIO      # 800 s

# Break-even precision: answering beats abstaining only above this. See p05_objective.py.
BREAK_EVEN_P = (COST_ABSTAIN * FP_RATIO - COST_ABSTAIN) / (SAVED_CORRECT + COST_ABSTAIN * FP_RATIO)


def net_value(tp: int, fp: int, abstained: int, fp_ratio: float = FP_RATIO) -> float:
    return SAVED_CORRECT * tp - COST_ABSTAIN * fp_ratio * fp - COST_ABSTAIN * abstained


@dataclass
class Outcome:
    """One scored line."""
    line_id: str
    tenant: str
    segment: str
    channel: str
    gt: str                      # "" means the correct action is to abstain
    decision: Decision
    latency_ms: float = 0.0

    @property
    def answerable(self) -> bool:
        return bool(self.gt)

    @property
    def is_auto(self) -> bool:
        return self.decision.decision == AUTO

    @property
    def tp(self) -> bool:
        return self.is_auto and self.decision.item_code == self.gt and self.answerable

    @property
    def fp(self) -> bool:
        return self.is_auto and not self.tp

    @property
    def in_top3(self) -> bool:
        return self.answerable and self.gt in [c.item_code for c in self.decision.candidates[:3]]


@dataclass
class Report:
    label: str
    n: int = 0
    tp: int = 0
    fp: int = 0
    abstained: int = 0
    answerable: int = 0
    unanswerable: int = 0
    correctly_refused: int = 0
    recall_at_3: float = 0.0
    abstain_recall_at_3: float = 0.0
    cross_tenant: int = 0
    reason_codes: dict = field(default_factory=dict)

    @property
    def coverage(self) -> float:
        return (self.tp + self.fp) / self.n if self.n else 0.0

    @property
    def precision(self) -> float | None:
        d = self.tp + self.fp
        return self.tp / d if d else None

    @property
    def net(self) -> float:
        return net_value(self.tp, self.fp, self.abstained)

    @property
    def net_per_line(self) -> float:
        return self.net / self.n if self.n else 0.0

    @property
    def accuracy(self) -> float:
        """Share of lines where the action taken was the right one.

        Kept only so that §6.2's question can be answered with a number: this is the
        metric that would have been reported by default, and on this data it ranks a
        matcher that destroys 30,000 operator-seconds ABOVE one that does nothing.
        It counts a correct refusal and a correct answer as the same event, which is
        precisely the collapse the 20x cost asymmetry forbids.
        """
        return (self.tp + self.correctly_refused) / self.n if self.n else 0.0

    @property
    def refusal_precision(self) -> float | None:
        """Of lines with no correct answer, the share we did not auto-answer."""
        return self.correctly_refused / self.unanswerable if self.unanswerable else None


def score(outcomes: list[Outcome], label: str = "all") -> Report:
    r = Report(label=label, n=len(outcomes))
    top3_hits = abstain_answerable = abstain_top3 = 0
    for o in outcomes:
        r.answerable += o.answerable
        r.unanswerable += not o.answerable
        if o.is_auto:
            r.tp += o.tp
            r.fp += o.fp
        else:
            r.abstained += 1
            r.correctly_refused += not o.answerable
            if o.answerable:
                abstain_answerable += 1
                abstain_top3 += o.in_top3
        top3_hits += o.in_top3
        r.reason_codes[o.decision.reason_code] = r.reason_codes.get(o.decision.reason_code, 0) + 1
        prefix = {"acme": "ACM-", "nordic": "NRD-"}.get(o.tenant)
        if prefix:
            codes = ([o.decision.item_code] if o.decision.item_code else []) + \
                    [c.item_code for c in o.decision.candidates]
            r.cross_tenant += sum(1 for c in codes if c and not c.startswith(prefix))
    r.recall_at_3 = top3_hits / r.answerable if r.answerable else 0.0
    r.abstain_recall_at_3 = abstain_top3 / abstain_answerable if abstain_answerable else 0.0
    return r


def operating_curve(outcomes: list[Outcome], points: int = 25) -> list[dict]:
    """Precision against coverage as the confidence floor sweeps, not one point (§6.2).

    Holds the matcher's structural refusals fixed and moves only the score floor: a line
    is eligible only if the matcher produced a candidate for it, so `not_an_item` and
    `ambiguous_twins` abstentions never re-enter the answer set at a lower threshold.
    That is deliberate - those refusals are decisions about the question, not about the
    score, and sweeping them would make the curve describe a system nobody would ship.
    """
    # Predicted code is the answer if there is one, else the top candidate. Reading only
    # candidates[0] would make a matcher that answers without publishing candidates
    # invisible to the sweep, which is how a curve ends up describing nothing.
    eligible = [(o, o.decision.item_code or o.decision.candidates[0].item_code,
                 o.decision.confidence)
                for o in outcomes if o.decision.item_code or o.decision.candidates]
    if not eligible:
        return [{"threshold": 0.0, "coverage": 0.0, "precision": None,
                 "net": net_value(0, 0, len(outcomes)), "n_auto": 0}]
    confs = sorted({c for _, _, c in eligible})
    step = max(1, len(confs) // points)
    out = []
    for t in confs[::step] + [confs[-1] + 1e-9]:
        tp = fp = 0
        for o, code, conf in eligible:
            if conf >= t:
                if o.answerable and code == o.gt:
                    tp += 1
                else:
                    fp += 1
        n_auto = tp + fp
        out.append({"threshold": round(t, 4), "coverage": n_auto / len(outcomes),
                    "precision": (tp / n_auto) if n_auto else None,
                    "net": net_value(tp, fp, len(outcomes) - n_auto), "n_auto": n_auto})
    return out


def latency_summary(outcomes: list[Outcome]) -> dict:
    lat = sorted(o.latency_ms for o in outcomes)
    if not lat:
        return {}
    return {"p50_ms": statistics.median(lat),
            "p95_ms": lat[max(0, (len(lat) * 95 + 99) // 100 - 1)],   # nearest rank
            "max_ms": lat[-1], "mean_ms": statistics.fmean(lat)}
