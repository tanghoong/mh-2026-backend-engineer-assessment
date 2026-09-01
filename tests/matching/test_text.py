"""Normalisation rules, one test per rule, each traceable to a line in the data.

Small and boring on purpose. Normalisation is the layer a live change in the walkthrough
is most likely to land on ("buyers started writing 4inch"), so it needs one obvious home
and tests that say what each rule is for.
"""
from __future__ import annotations

import pytest

from src.matching.text import dice, normalise, trigrams


@pytest.mark.parametrize("raw, expected", [
    # PDF spacing damage - ACM-T-0002
    ("Vermmont  PVC  Pipe  20mmC  lass  E", "vermmont pvc pipe 20mmc lass e"),
    # slash-delimited, no spaces at all - ACM-T-0009
    ('Remax/Ball/Valve/2"/SS304', "remax ball valve 2in ss304"),
    # inch marks, three spellings of one size
    ('Angle Grinder Disc 4"', "angle grinder disc 4in"),
    ("Angle Grinder Disc 4 in", "angle grinder disc 4 in"),
    ("Angle Grinder Disc 4in", "angle grinder disc 4in"),
    # case and padding
    ("  KANTO Hex Bolt  ", "kanto hex bolt"),
])
def test_normalisation_rules(raw, expected):
    assert normalise(raw) == expected


@pytest.mark.parametrize("raw, kept", [
    ("Sisu Prawn 21/25 1kg", "21/25"),      # a size ratio, not two tokens
    ('Ball Valve 1-1/4" PVC', "1-1/4in"),   # a fraction size
])
def test_digit_slashes_survive(raw, kept):
    """A slash between digits is part of a size; between anything else it is a delimiter.
    An earlier rule only split letter/letter and left `valve/2in` joined."""
    assert kept in normalise(raw).split()


def test_trigrams_are_token_scoped_not_string_scoped():
    """Padding per token, so word boundaries carry information and token order does not."""
    assert trigrams(normalise("hex bolt")) == trigrams(normalise("bolt hex"))
    assert " he" in trigrams("hex")


def test_dice_survives_the_typos_token_overlap_cannot():
    """ACM-H-5002 is 'HitxeH ex Bolt M10x75' - a transposition across a word boundary.
    It shares no whole token with the catalogue entry, which is why scoring is on
    characters and not on tokens."""
    typo = normalise("HitxeH ex Bolt M10x75 Zinc Plated")
    truth = normalise("Hitex Hex Bolt M10x75 Zinc Plated")
    assert set(typo.split()) & set(truth.split()) != set(truth.split())   # tokens disagree
    assert dice(trigrams(typo), trigrams(truth)) > 0.7                    # characters do not


def test_dice_is_symmetric_and_bounded():
    a, b = trigrams("hex bolt"), trigrams("hex bolt m8")
    assert dice(a, b) == dice(b, a)
    assert dice(a, a) == 1.0
    assert dice(a, set()) == 0.0
