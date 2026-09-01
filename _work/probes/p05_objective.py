#!/usr/bin/env python3
"""Derives the operating point for DESIGN.md Task 1. Read-only, stdlib.

Every number quoted in DESIGN.md section 1 comes from here, so it can be re-derived
in the walkthrough rather than recalled.

    python3 _work/probes/p05_objective.py
"""
import math

SAVED_CORRECT = 20.0     # seconds saved by a correct auto-match
COST_ABSTAIN = 40.0      # seconds, human review queue
RATIO = 20.0             # a wrong auto-match costs RATIO x an abstention


def breakeven(ratio: float) -> float:
    """Minimum P(correct) at which answering beats abstaining.

    E[auto]     = SAVED_CORRECT * p - COST_ABSTAIN * ratio * (1 - p)
    E[abstain]  = -COST_ABSTAIN
    Answer iff E[auto] > E[abstain].
    """
    return (COST_ABSTAIN * ratio - COST_ABSTAIN) / (SAVED_CORRECT + COST_ABSTAIN * ratio)


def net_value(n_auto_correct, n_auto_wrong, n_abstain, ratio=RATIO):
    return (SAVED_CORRECT * n_auto_correct
            - COST_ABSTAIN * ratio * n_auto_wrong
            - COST_ABSTAIN * n_abstain)


def wilson_lower(p_hat: float, n: int, z: float = 1.645) -> float:
    """One-sided 95% lower confidence bound on a proportion."""
    if n == 0:
        return 0.0
    d = 1 + z * z / n
    centre = p_hat + z * z / (2 * n)
    half = z * math.sqrt(p_hat * (1 - p_hat) / n + z * z / (4 * n * n))
    return (centre - half) / d


if __name__ == "__main__":
    print("== break-even precision vs cost ratio ==")
    print("  ratio   p*        meaning")
    for k in (1, 2, 3, 5, 10, 20, 30, 50):
        print(f"  {k:>4}x   {breakeven(k):.4f}    answer only when P(correct) > {breakeven(k):.1%}")

    p_star = breakeven(RATIO)
    print(f"\n  at the stated {RATIO:.0f}x: p* = {p_star:.4f}  ({p_star:.2%})")
    print(f"  at 3x (walkthrough scenario): p* = {breakeven(3):.4f}  ({breakeven(3):.2%})")

    print("\n== is a measured precision floor safe at our sample size? ==")
    print("  train n=420. Assume ~60% auto coverage -> ~252 auto decisions.")
    print("  A floor is only safe if its one-sided 95% LOWER bound clears p*.")
    print(f"\n  floor   n=252 lower   n=180 lower   clears p*={p_star:.4f}?")
    for floor in (0.90, 0.93, 0.95, 0.955, 0.96, 0.97, 0.98, 0.99):
        lo252 = wilson_lower(floor, 252)
        lo180 = wilson_lower(floor, 180)
        ok = "yes" if lo252 > p_star else "NO"
        ok2 = "yes" if lo180 > p_star else "NO"
        print(f"  {floor:.3f}   {lo252:.4f}       {lo180:.4f}       {ok:<4} (n=180: {ok2})")

    print("\n== null matcher: abstain on everything, 300 holdout lines ==")
    print(f"  net value = {net_value(0, 0, 300):.0f} operator-seconds")
    print("  Anything shipped must beat this. It is the zero point, not zero.")

    print("\n== what one false positive costs, in correct answers ==")
    print(f"  1 wrong auto = {COST_ABSTAIN * RATIO / SAVED_CORRECT:.0f} correct autos wiped out")
    print(f"  1 wrong auto = {COST_ABSTAIN * RATIO / COST_ABSTAIN:.0f} abstentions")

    print("\n== the alias lane as measured (TR-01), 64 train lines ==")
    naive = net_value(23, 41, 0)
    fixed = net_value(64, 0, 0)
    abstain_all = net_value(0, 0, 64)
    print(f"  naive alias_exact -> auto   : {naive:>9.0f} s   (precision 35.9%)")
    print(f"  abstain on all 64           : {abstain_all:>9.0f} s")
    print(f"  after supersession redirect : {fixed:>9.0f} s   (precision 100%)")
    print("  The naive lane is worse than not having the alias table at all.")
