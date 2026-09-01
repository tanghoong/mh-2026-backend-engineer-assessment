#!/usr/bin/env python3
"""The evaluation harness. One command, reproducible, offline.

    python3 -m src.eval.harness                       # default matcher, train set
    python3 -m src.eval.harness --matcher null        # the zero point
    python3 -m src.eval.harness --matcher naive_alias # the obvious mistake, measured
    python3 -m src.eval.harness --curve --json out.json

Built before the matcher, on purpose (DECISIONS.md D-08): a matcher without a scorer can
only be guessed at, and §6 grades the harness in its own right.

What it enforces beyond reporting numbers:

* **Determinism** (§5.1) - `--check-determinism` runs twice and diffs the outputs.
* **Latency** (§5.1) - p95 measured per line, nearest rank, and reported rather than
  assumed. Index construction happens before timing starts, so cold caches are excluded
  as the brief allows, and that exclusion is stated rather than hidden.
* **Tenant isolation** (§5.4) - a hard fail. Counted on `item_code` *and* on every
  candidate, because a leaked candidate is a leak that has not been returned yet.
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import time

from ..contracts import OrderLine
from . import metrics as M
from .segments import SEGMENTS, segment

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


def load(name: str) -> list[dict]:
    with open(DATA / name, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def build(name: str):
    from ..matching import baselines
    table = {"null": baselines.NullMatcher, "naive_alias": baselines.NaiveAliasMatcher}
    try:
        from ..matching.pipeline import Pipeline           # the real matcher, once it exists
        table["pipeline"] = Pipeline
    except ImportError:
        pass
    if name not in table:
        raise SystemExit(f"unknown matcher {name!r}; available: {', '.join(sorted(table))}")
    return table[name]()


def run(matcher, rows: list[dict]) -> list[M.Outcome]:
    """Match every line, timing each call. Construction cost is already paid."""
    out = []
    for row in rows:
        line = OrderLine.from_row(row)
        t0 = time.perf_counter()
        decision = matcher.match(line)
        dt = (time.perf_counter() - t0) * 1000.0
        if decision.line_id != line.line_id:
            raise AssertionError(f"{matcher.name} returned a decision for the wrong line")
        out.append(M.Outcome(line_id=line.line_id, tenant=line.tenant,
                             segment=segment(line), channel=line.channel,
                             gt=(row.get("gt_item_code") or "").strip(),
                             decision=decision, latency_ms=dt))
    return out


# ------------------------------------------------------------------ presentation

def _row(r: M.Report, width: int = 17) -> str:
    p = f"{r.precision:6.1%}" if r.precision is not None else "     -"
    rf = f"{r.refusal_precision:7.0%}" if r.refusal_precision is not None else "      -"
    return (f"  {r.label:<{width}}{r.n:>5}{r.coverage:>9.1%}{p}"
            f"{r.tp:>6}{r.fp:>5}{rf}{r.recall_at_3:>9.1%}"
            f"{r.accuracy:>9.1%}{r.net:>11,.0f}")


def report(outcomes: list[M.Outcome], matcher_name: str, show_curve: bool) -> dict:
    overall = M.score(outcomes)
    head = (f"  {'segment':<17}{'n':>5}{'cover':>9}{'prec':>6}"
            f"{'TP':>6}{'FP':>5}{'refuse':>7}{'rec@3':>9}{'acc':>9}{'net (s)':>11}")

    print(f"\n=== {matcher_name} on {overall.n} labelled lines ===")
    print(f"  cost model: +{M.SAVED_CORRECT:.0f} correct / -{M.COST_ABSTAIN:.0f} abstain "
          f"/ -{M.COST_WRONG:.0f} wrong  ->  break-even precision {M.BREAK_EVEN_P:.2%}")
    print("\n" + head)
    print("  " + "-" * (len(head) - 2))
    print(_row(overall).replace(f"  {'all':<17}", f"  {'ALL':<17}") if False else _row(overall))

    print("\n  by noise class (defined in segments.py, computed from the raw line only)")
    for s in SEGMENTS:
        sub = [o for o in outcomes if o.segment == s]
        if sub:
            print(_row(M.score(sub, s)))

    print("\n  by tenant")
    for t in sorted({o.tenant for o in outcomes}):
        print(_row(M.score([o for o in outcomes if o.tenant == t], t)))

    print("\n  by channel")
    for c in sorted({o.channel for o in outcomes}):
        print(_row(M.score([o for o in outcomes if o.channel == c], c)))

    lat = M.latency_summary(outcomes)
    budget = "PASS" if lat["p95_ms"] <= 250 else "OVER BUDGET"
    print(f"\n  latency   p50 {lat['p50_ms']:.3f} ms   p95 {lat['p95_ms']:.3f} ms   "
          f"max {lat['max_ms']:.3f} ms   (budget 250 ms p95 -> {budget})")

    null_net = M.net_value(0, 0, overall.n)
    print(f"  net value {overall.net:>+10,.0f} s   "
          f"({overall.net_per_line:+.1f} s/line)   null matcher {null_net:+,.0f} s   "
          f"delta {overall.net - null_net:+,.0f} s")
    print(f"  cross-tenant violations: {overall.cross_tenant}"
          + ("   <-- HARD FAIL (brief 5.4)" if overall.cross_tenant else ""))
    print("  reason codes: " + ", ".join(
        f"{k}={v}" for k, v in sorted(overall.reason_codes.items(), key=lambda kv: -kv[1])))

    curve = M.operating_curve(outcomes)
    if show_curve:
        print(f"\n  operating point curve ({len(curve)} points; structural refusals held fixed)")
        print(f"    {'floor':>8}{'coverage':>10}{'precision':>11}{'auto':>7}{'net (s)':>11}")
        for pt in curve:
            pr = f"{pt['precision']:10.1%}" if pt["precision"] is not None else "         -"
            print(f"    {pt['threshold']:>8.4f}{pt['coverage']:>10.1%}{pr}"
                  f"{pt['n_auto']:>7}{pt['net']:>11,.0f}")

    return {"matcher": matcher_name, "overall": vars(overall) | {
        "coverage": overall.coverage, "precision": overall.precision, "net": overall.net,
        "refusal_precision": overall.refusal_precision},
        "latency": lat, "curve": curve,
        "by_segment": {s: vars(M.score([o for o in outcomes if o.segment == s], s))
                       for s in SEGMENTS if any(o.segment == s for o in outcomes)}}


def _main() -> None:
    ap = argparse.ArgumentParser(description="Evaluate a matcher on the labelled train set.")
    ap.add_argument("--matcher", default="null")
    ap.add_argument("--data", default="order_lines_train.csv")
    ap.add_argument("--curve", action="store_true", help="print the precision/coverage sweep")
    ap.add_argument("--json", help="also write the full report here")
    ap.add_argument("--check-determinism", action="store_true",
                    help="run twice and require identical decisions (§5.1)")
    ap.add_argument("--compare", nargs="*", metavar="MATCHER",
                    help="score several matchers side by side (§6.2: accuracy vs net value)")
    args = ap.parse_args()

    rows = load(args.data)

    if args.compare is not None:
        names = args.compare or ["null", "naive_alias"]
        print(f"\n=== accuracy against net value, {len(rows)} labelled lines ===")
        print(f"  {'matcher':<16}{'accuracy':>10}{'coverage':>10}{'precision':>11}"
              f"{'net (s)':>12}{'vs null':>11}")
        null_net = M.net_value(0, 0, len(rows))
        for nm in names:
            r = M.score(run(build(nm), rows))
            pr = f"{r.precision:10.1%}" if r.precision is not None else "         -"
            print(f"  {nm:<16}{r.accuracy:>10.1%}{r.coverage:>10.1%}{pr}"
                  f"{r.net:>12,.0f}{r.net - null_net:>+11,.0f}")
        print("\n  Accuracy and net value disagree about which of these to ship.")
        print("  Accuracy counts a correct refusal and a correct answer as the same event;")
        print("  the cost model prices a wrong answer at 20x a refusal. See EVAL.md section 2.")
        return

    matcher = build(args.matcher)          # construction excluded from latency, as allowed
    outcomes = run(matcher, rows)
    payload = report(outcomes, matcher.name, args.curve)

    if args.check_determinism:
        again = run(build(args.matcher), rows)
        a = [(o.line_id, o.decision.item_code, o.decision.decision, o.decision.reason_code,
              round(o.decision.confidence, 9), o.decision.top3()) for o in outcomes]
        b = [(o.line_id, o.decision.item_code, o.decision.decision, o.decision.reason_code,
              round(o.decision.confidence, 9), o.decision.top3()) for o in again]
        diff = [x for x, y in zip(a, b) if x != y]
        print(f"\n  determinism: {'PASS' if not diff else f'FAIL on {len(diff)} lines'}"
              f"  (two runs, fresh construction each time)")
        if diff:
            raise SystemExit(1)

    if args.json:
        pathlib.Path(args.json).write_text(json.dumps(payload, indent=1, default=str),
                                          encoding="utf-8")
        print(f"\n  wrote {args.json}")


if __name__ == "__main__":
    _main()
