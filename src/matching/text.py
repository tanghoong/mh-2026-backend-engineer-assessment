#!/usr/bin/env python3
"""P3-2 stage 0 — text normalisation, and the lexical similarity it feeds.

Deliberately small. Every rule here is one the data showed a need for, and each is
listed so it can be pointed at during a walkthrough rather than defended as a blob:

  * case and whitespace          "Vermmont  PVC  Pipe" (PDF spacing damage)
  * delimiter joining            "Remax/Ball/Valve/2\\"/SS304"
  * inch marks                   4" and 4 in and 4in are the same size
  * fraction spacing             1-1/4" must survive as one token

The similarity is **character trigram Dice**, not token overlap. Token overlap fails on
exactly the population that needs help: `HitxeH ex Bolt` (transposed characters across a
word boundary) and `Vermmont` (doubled letter) share no whole token with the catalogue
entry, but share most of their trigrams. Dice rather than Jaccard because item names are
much longer than order lines and Jaccard would penalise every match for that.
"""
from __future__ import annotations

import re

# Order language, not product identity. Buyers wrap the item in a request ("pls send
# ... urgent") and append how many they want ("x24", "3 cartons"); neither narrows which
# item it is, and both dilute a character-similarity score by padding the query with
# trigrams no catalogue entry can match.
#
# Measured, not assumed: dropping these lifts coverage 26.2% -> 28.3% with precision
# unchanged at 99.2%. The alternative - dropping every query token absent from the tenant
# vocabulary - reaches 30.0% coverage but falls to 96.0% precision and a WORSE net value,
# because it also deletes the misspellings ("vermmont", "ttape") that the trigrams are
# there to absorb. See DECISIONS.md D-26.
STOP_WORDS = frozenset("""
pls please send sending urgent urgently need needed want item items order kindly asap
re and the for of no nos qty
pc pcs unit units ea each case cases dozen dz pkt packet pack carton ctn box bag tin
roll set sets
""".split())
_PACK_QTY = re.compile(r"^x\d+$|^\d+x$")

_INCH = re.compile(r'(\d)\s*"')
_SPLIT = re.compile(r"[^0-9a-z/\-.]+")
_TRIM = re.compile(r"^[/\-.]+|[/\-.]+$")


def normalise(text: str) -> str:
    """Lowercase, collapse damage, keep size tokens intact."""
    s = text.lower()
    s = _INCH.sub(r"\1in", s)              # 4" -> 4in, before slashes are touched
    s = s.replace("|", " ")
    # A slash is a delimiter unless BOTH sides are digits, in which case it is a fraction
    # or a size ratio (21/25, 1/4) and has to survive. An earlier version only split
    # letter/letter and left "valve/2in" joined, which is a delimiter the buyer typed.
    s = re.sub(r"(?<![0-9])/|/(?![0-9])", " ", s)
    s = _SPLIT.sub(" ", s)
    toks = [t for t in (_TRIM.sub("", tok) for tok in s.split()) if t]
    kept = [t for t in toks if t not in STOP_WORDS and not _PACK_QTY.match(t)]
    # Never normalise a line to nothing: a query made entirely of order language still has
    # to reach the not-an-item detector rather than vanish into an empty-text abstention.
    return " ".join(kept or toks)


def trigrams(text: str) -> set[str]:
    """Character trigrams over the normalised string, space-padded per token."""
    out: set[str] = set()
    for tok in text.split():
        padded = f" {tok} "
        out.update(padded[i:i + 3] for i in range(len(padded) - 2))
    return out


def dice(a: set[str], b: set[str]) -> float:
    """2|A n B| / (|A| + |B|). Symmetric, and unbiased by length difference."""
    if not a or not b:
        return 0.0
    return 2.0 * len(a & b) / (len(a) + len(b))


if __name__ == "__main__":
    samples = [
        'Remax/Ball/Valve/2"/SS304',
        "Vermmont  PVC  Pipe  20mmC  lass  E",
        "HitxeH ex Bolt M10x75 Zinc Plated",
        'Hitex Angle Grinder Disc 7" Flap',
        "Sisu Prawn 21/25 1kg",
        "Nordvik Full Cream Milk Fresh 200ml",
    ]
    for s in samples:
        print(f"  {s!r}\n    -> {normalise(s)!r}")
    a, b = trigrams(normalise("HitxeH ex Bolt M10x75")), trigrams(normalise("Hitex Hex Bolt M10x75"))
    print(f"\n  dice(typo, truth) = {dice(a, b):.3f}")
