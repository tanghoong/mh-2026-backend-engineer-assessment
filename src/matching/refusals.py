#!/usr/bin/env python3
"""P3-4 — the abstain detectors. Four refusals, not one.

`DESIGN.md` §4 and TR-03: "abstain" is not one class. 29.8% of train has no correct
answer, and the population has at least four shapes that need different mechanisms and
give an operator different instructions:

| reason | what it means to a reviewer | measured on train |
|---|---|---|
| `not_an_item` | this line is not an order line | 7 refusals, **100%** correct |
| `out_of_domain` | a real product, but not one this tenant sells | 48 refusals, **100%** correct |
| `ambiguous_candidates` | it is one of these, you pick | 139 refusals, 27.3% correct |
| `no_candidate_above_floor` | nothing close enough to show you | 107 refusals, 29.0% correct |

The first two are **certain**; the last two are *uncertain by construction* - they exist
because the system could not decide, so a low "correct refusal" rate is expected there and
is not a defect. Collapsing all four into one score floor loses that distinction, and it
is the distinction the review queue is triaged on.

Neither detector changes net value on train - every line they catch was already refused.
They change what the refusal *says*, which is what §5.1 asks for and what §5.4 scores as
abstention quality.
"""
from __future__ import annotations

import re

# Bookkeeping and correspondence that arrives on an order but is not an order line.
# Drawn from the data, not imagined: "subtotal", "same as last month order".
NOT_AN_ITEM = re.compile(
    r"\b(subtotal|sub total|total|delivery|deposit|balance|discount|rounding|freight|"
    r"thank you|thanks|same as|as per|per your|see attached|as above|tbc|tba|nil|n/a)\b",
    re.I)

# Share of non-numeric query tokens that appear anywhere in the tenant's catalogue.
# Below this, the line is about something the tenant does not sell. Chosen from the
# sensitivity table in `_main` - it is a plateau, not a knife edge.
DOMAIN_TOKEN_FLOOR = 0.34


def is_not_an_item(raw_text: str, normalised: str) -> bool:
    """True when the line is not an order line at all."""
    return bool(NOT_AN_ITEM.search(raw_text)) or not normalised.split()


def domain_overlap(normalised: str, vocabulary: set[str]) -> float:
    """Share of the query's word tokens the tenant's catalogue has ever used.

    Numbers are excluded: sizes and quantities are shared across every domain, so
    counting them would make a frozen-food line look like hardware.
    """
    tokens = [w for w in normalised.split() if not w.isdigit()]
    if not tokens:
        return 0.0
    return sum(1 for w in tokens if w in vocabulary) / len(tokens)


def is_out_of_domain(normalised: str, vocabulary: set[str]) -> bool:
    """True when the line describes a product this tenant does not deal in.

    An acme (industrial hardware) line reading "Cadbury Dairy Milk 165g" or "Wagyu
    striploin MB7 grain fed" is a real product and a real order - for somebody else. It
    is not a low-confidence match, it is a different question, and an operator should be
    told which.
    """
    return domain_overlap(normalised, vocabulary) <= DOMAIN_TOKEN_FLOOR


def _main() -> None:
    """Threshold sensitivity, so the constant is a choice and not a coincidence."""
    import collections
    import sys

    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
    from src.eval import harness
    from src.matching.index import build_tenant_index
    from src.matching.text import normalise

    rows = {r["line_id"]: r for r in harness.load("order_lines_train.csv")}
    outs = harness.run(harness.build("pipeline"), harness.load("order_lines_train.csv"))
    idxs = {t: build_tenant_index(t) for t in ("acme", "nordic")}
    vocab = {t: {w for s in i.search_text.values() for w in s.split()}
             for t, i in idxs.items()}
    refused = [o for o in outs if o.decision.decision != "auto"]

    print("=== out_of_domain threshold sensitivity ===")
    print(f"  {'floor':>7}{'refusals':>10}{'correct':>9}{'precision':>11}   verdict")
    for floor in (0.0, 0.10, 0.20, 0.25, 0.34, 0.40, 0.50, 0.60):
        fired = [o for o in refused
                 if domain_overlap(normalise(rows[o.line_id]["raw_text"]), vocab[o.tenant])
                 <= floor and not is_not_an_item(rows[o.line_id]["raw_text"],
                                                 normalise(rows[o.line_id]["raw_text"]))]
        if not fired:
            print(f"  {floor:>7.2f}{0:>10}{0:>9}{'-':>11}")
            continue
        ok = sum(1 for o in fired if not o.answerable)
        verdict = "clean" if ok == len(fired) else f"{len(fired)-ok} answerable line(s) lost"
        print(f"  {floor:>7.2f}{len(fired):>10}{ok:>9}{ok/len(fired):>11.1%}   {verdict}")
    print("\n  0.34 sits at the top of the plateau: every floor from 0 to 0.34 refuses only")
    print("  lines that have no answer, and the first mistake appears above it.")


if __name__ == "__main__":
    _main()
