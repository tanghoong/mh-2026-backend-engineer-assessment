#!/usr/bin/env python3
"""P3-8 — produce `predictions.csv` over the holdout set.

    python3 -m src.predict                      # writes predictions.csv
    python3 -m src.predict --check              # verify an existing file

Schema is fixed by §5.3 and is not negotiable:

    line_id,item_code,confidence,decision,reason_code,candidates

* `item_code` blank when abstaining
* `confidence` a float in [0,1], and here a *measured probability* - see calibration.py
* `decision` one of auto / review / reject
* `reason_code` a short stable token from a closed set
* `candidates` up to 3 `item_code:score` pairs, `|`-separated, best first

The holdout is unlabelled and scored by the graders, so nothing here may look at
`order_lines_train.csv`. The only thing carried across is the matcher itself.
"""
from __future__ import annotations

import argparse
import csv
import pathlib
import sys
import time

from .contracts import AUTO, DECISIONS, OrderLine
from .eval import harness
from .eval.metrics import latency_summary
from .matching.calibration import CALIBRATION

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "predictions.csv"
HEADER = ["line_id", "item_code", "confidence", "decision", "reason_code", "candidates"]

# Every reason the matcher may emit. An unregistered code fails `--check` rather than
# reaching a grader, because a reason_code nobody can look up is not an explanation.
KNOWN_REASONS = {
    "alias_exact", "alias_exact_superseded_redirect", "alias_ambiguous",
    "alias_unresolvable", "barcode_unique", "barcode_ambiguous", "barcode_no_match",
    "lexical_unique", "ambiguous_candidates", "no_candidate_above_floor",
    "no_lexical_candidate", "not_an_item", "out_of_domain", "empty_text",
    "unknown_tenant",
}


def predict(data: str = "order_lines_holdout.csv") -> tuple[list[dict], dict]:
    rows = harness.load(data)
    matcher = harness.build("pipeline")          # construction excluded from the timing
    out, timings = [], []
    for row in rows:
        line = OrderLine.from_row(row)
        t0 = time.perf_counter()
        d = matcher.match(line)
        timings.append((time.perf_counter() - t0) * 1000.0)
        out.append({"line_id": d.line_id,
                    "item_code": d.item_code or "",
                    "confidence": f"{d.confidence:.4f}",
                    "decision": d.decision,
                    "reason_code": d.reason_code,
                    "candidates": d.top3()})
    lat = latency_summary([_Timing(ms) for ms in timings])
    return out, lat


class _Timing:
    """Adapter so `latency_summary` can be reused rather than reimplemented."""

    def __init__(self, ms: float) -> None:
        self.latency_ms = ms


def write(rows: list[dict], path: pathlib.Path = OUT) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=HEADER, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def check(path: pathlib.Path = OUT, data: str = "order_lines_holdout.csv") -> list[str]:
    """Validate a written file against §5.3 and against the input it claims to cover.

    Returns a list of problems. Deliberately checks the *file*, not the objects that
    produced it - a schema the code satisfies and the CSV does not is still a failure.
    """
    problems: list[str] = []
    expected = [r["line_id"] for r in harness.load(data)]
    tenant_of = {r["line_id"]: r["tenant"] for r in harness.load(data)}
    prefix = {"acme": "ACM-", "nordic": "NRD-"}

    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != HEADER:
            problems.append(f"header is {reader.fieldnames}, must be {HEADER}")
        got = list(reader)

    if [r["line_id"] for r in got] != expected:
        problems.append(f"line_ids do not match {data} exactly, in order "
                        f"({len(got)} rows vs {len(expected)})")

    for r in got:
        lid = r["line_id"]
        if r["decision"] not in DECISIONS:
            problems.append(f"{lid}: decision {r['decision']!r}")
        if (r["decision"] == AUTO) != bool(r["item_code"]):
            problems.append(f"{lid}: item_code must be set iff decision is auto")
        try:
            conf = float(r["confidence"])
            if not 0.0 <= conf <= 1.0:
                problems.append(f"{lid}: confidence {conf} outside [0,1]")
        except ValueError:
            problems.append(f"{lid}: confidence {r['confidence']!r} is not a float")
        if r["reason_code"] not in KNOWN_REASONS:
            problems.append(f"{lid}: unregistered reason_code {r['reason_code']!r}")

        pairs = [p for p in r["candidates"].split("|") if p]
        if len(pairs) > 3:
            problems.append(f"{lid}: {len(pairs)} candidates, at most 3 allowed")
        scores = []
        for pair in pairs:
            code, _, score = pair.rpartition(":")
            if not code:
                problems.append(f"{lid}: candidate {pair!r} is not code:score")
                continue
            scores.append(float(score))
            if (p := prefix.get(tenant_of[lid])) and not code.startswith(p):
                problems.append(f"{lid}: CROSS-TENANT candidate {code} for {tenant_of[lid]}")
        if scores != sorted(scores, reverse=True):
            problems.append(f"{lid}: candidates are not best-first")
        code = r["item_code"]
        if code and (p := prefix.get(tenant_of[lid])) and not code.startswith(p):
            problems.append(f"{lid}: CROSS-TENANT answer {code} for {tenant_of[lid]}")
    return problems


def _summarise(rows: list[dict], lat: dict) -> None:
    import collections

    n = len(rows)
    auto = sum(1 for r in rows if r["decision"] == AUTO)
    reasons = collections.Counter(r["reason_code"] for r in rows)
    print(f"  {n} rows, {auto} auto ({auto / n:.1%} coverage), "
          f"{n - auto} abstained")
    print(f"  latency  p50 {lat['p50_ms']:.3f} ms   p95 {lat['p95_ms']:.3f} ms   "
          f"max {lat['max_ms']:.3f} ms   (budget 250 ms p95 -> "
          f"{'PASS' if lat['p95_ms'] <= 250 else 'OVER BUDGET'})")
    print("  reason codes:")
    for k, v in reasons.most_common():
        pool = CALIBRATION.get(k)
        note = f"   confidence {pool[1]} (measured {pool[2]}/{pool[3]} on train)" if pool else ""
        print(f"    {k:<34}{v:>5}{note}")


def _main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="order_lines_holdout.csv")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--check", action="store_true",
                    help="validate an existing file instead of writing one")
    args = ap.parse_args()
    path = pathlib.Path(args.out)

    if args.check:
        problems = check(path, args.data)
        print(f"=== checking {path.name} against section 5.3 ===")
        for p in problems:
            print(f"  FAIL  {p}")
        print(f"  {'OK - schema, ordering, domains and tenant isolation all hold' if not problems else f'{len(problems)} problem(s)'}")
        sys.exit(1 if problems else 0)

    rows, lat = predict(args.data)
    write(rows, path)
    print(f"=== wrote {path.name} from {args.data} ===")
    _summarise(rows, lat)
    problems = check(path, args.data)
    print(f"\n  self-check: {'OK' if not problems else problems}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    _main()
