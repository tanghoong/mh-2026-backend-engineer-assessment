#!/usr/bin/env python3
"""Noise-class segmentation for the evaluation harness.

§6.1 asks for per-noise-class breakdowns and notes the classes are *not* labelled in
the shipped data, so they have to be defined and justified. Two rules shaped this one:

1. **Computable from the raw line alone.** A segmentation that reads `gt_item_code`
   would be describing the answer key, not the input distribution, and would be
   unavailable on the holdout — where the breakdown actually has to hold up.
2. **A partition, not a set of overlapping flags.** Priority-ordered, so every line
   lands in exactly one class. Overlapping tags make per-class precision impossible to
   read: a line counted in three classes moves three numbers at once.

The order is by *which lane will decide the line*, not by which words it contains. A
line carrying a buyer SKU is an `identifier` line even if it also has format damage,
because the identifier lane resolves it first and the format damage never gets a vote.

    python3 -m src.eval.segments      # print the distribution and blank-label rates
"""
from __future__ import annotations

import re

from ..contracts import OrderLine

SIZE_TOKEN = re.compile(
    r'\b\d+(?:\.\d+)?\s*(?:kg|g|l|ml|mm|cm|m|in|")\b|\bM\d+x\d+\b|\b\d+/\d+\b|\b\d+"\b',
    re.I)
NON_ITEM = re.compile(
    r'\b(subtotal|total|delivery|deposit|balance|discount|rounding|same as|as per|thank)\b',
    re.I)
FORMAT_NOISE = re.compile(r'\S  +\S')          # collapsed/expanded spacing from PDF text
DELIMITED = re.compile(r'^[^\s]*[/|][^\s]*$')  # slash- or pipe-joined, no spaces at all

SEGMENTS = ("identifier", "non_item_marker", "underspecified", "format_noise",
            "sized", "plain")


def segment(line: OrderLine) -> str:
    """Assign one noise class. Priority order is significant; see module docstring."""
    text = line.raw_text

    # 1. An identifier is present, so a deterministic lane decides this line.
    if line.buyer_sku.strip() or line.raw_barcode.strip():
        return "identifier"

    # 2. Bookkeeping text that is not an item at all. Small but it is the class the
    #    abstain path exists for, so it is measured separately rather than diluted.
    if NON_ITEM.search(text):
        return "non_item_marker"

    # 3. Too little to identify a product: few tokens and no size to disambiguate a
    #    twin group. This is the population TR-04's ambiguity rule has to refuse.
    if len(text.split()) < 4 and not SIZE_TOKEN.search(text):
        return "underspecified"

    # 4. The words may be right but the shape is damaged - PDF spacing, slash-joined.
    if FORMAT_NOISE.search(text) or DELIMITED.match(text.strip()):
        return "format_noise"

    # 5. Carries a size/pack token, so twin arbitration has something to work with.
    if SIZE_TOKEN.search(text):
        return "sized"

    return "plain"


def _main() -> None:
    import collections
    import csv
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2]
    for name in ("order_lines_train.csv", "order_lines_holdout.csv"):
        rows = list(csv.DictReader(open(root / "data" / name, encoding="utf-8")))
        labelled = "gt_item_code" in rows[0]
        counts: dict = collections.Counter()
        blanks: dict = collections.Counter()
        for r in rows:
            s = segment(OrderLine.from_row(r))
            counts[s] += 1
            if labelled and not r["gt_item_code"].strip():
                blanks[s] += 1
        total = len(rows)
        base = sum(blanks.values()) / total if labelled else None
        print(f"\n{name}  (n={total})")
        head = f"  {'segment':<17}{'n':>5}{'share':>8}"
        print(head + (f"{'no-answer':>11}" if labelled else ""))
        for s in SEGMENTS:
            n = counts[s]
            row = f"  {s:<17}{n:>5}{n / total:>8.1%}"
            if labelled:
                row += f"{(blanks[s] / n if n else 0):>11.0%}"
            print(row)
        if labelled:
            print(f"  {'ALL':<17}{total:>5}{1:>8.0%}{base:>11.0%}")


if __name__ == "__main__":
    _main()
