#!/usr/bin/env python3
"""The contract between a matcher and everything that measures it.

Defined before either side exists so that the harness can be built and validated
against reference matchers first (DECISIONS.md D-08). A matcher is any callable
taking an OrderLine and returning a Decision; nothing else about it is assumed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

# `decision` values, per the brief §5.3.
AUTO, REVIEW, REJECT = "auto", "review", "reject"
DECISIONS = (AUTO, REVIEW, REJECT)


@dataclass(frozen=True)
class OrderLine:
    """One row of order_lines_*.csv, with the label stripped off.

    `gt_item_code` deliberately does not live here: the harness holds labels, the
    matcher never sees one. Making that structural rather than a convention is the
    cheapest available guard against leakage.
    """
    line_id: str
    tenant: str
    customer_id: str
    channel: str
    order_date: str
    raw_text: str
    qty: str = ""
    uom_text: str = ""
    unit_price: str = ""
    buyer_sku: str = ""
    raw_barcode: str = ""
    notes: str = ""

    @classmethod
    def from_row(cls, row: dict) -> "OrderLine":
        return cls(**{k: (row.get(k) or "") for k in cls.__dataclass_fields__})


@dataclass(frozen=True)
class Candidate:
    """One considered item, with the evidence that put it there."""
    item_code: str
    score: float
    lane: str = ""
    evidence: tuple = ()

    def render(self) -> str:
        return f"{self.item_code}:{self.score:.4f}"


@dataclass
class Decision:
    """What a matcher returns for one line.

    `confidence` must be comparable across lanes — that comparability is what the
    operating-point curve sweeps, and calibrating it is the matcher's job, not the
    harness's. `reason_code` is required even when answering: an operator in the review
    queue and an engineer grepping logs both need it (§5.1).
    """
    line_id: str
    item_code: str | None
    confidence: float
    decision: str
    reason_code: str
    candidates: list[Candidate] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.decision not in DECISIONS:
            raise ValueError(f"{self.line_id}: decision {self.decision!r} not in {DECISIONS}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"{self.line_id}: confidence {self.confidence} outside [0,1]")
        if not self.reason_code:
            raise ValueError(f"{self.line_id}: every decision needs a reason_code")
        if (self.decision == AUTO) != bool(self.item_code):
            raise ValueError(
                f"{self.line_id}: item_code must be set iff decision is {AUTO!r} "
                f"(got decision={self.decision!r}, item_code={self.item_code!r})")

    def top3(self) -> str:
        return "|".join(c.render() for c in self.candidates[:3])


class Matcher(Protocol):
    """Anything the harness can measure."""

    name: str

    def match(self, line: OrderLine) -> Decision: ...
