#!/usr/bin/env python3
"""Timing + equivalence harness for Task 4.

Stdlib only.

    # check your version against the shipped reference result
    python3 bench_report.py check --db ../data/perf.sqlite \
        --sql my_report.sql --repeat 5 --budget-s 10

The reference (../data/report_reference.json.gz) ships with the assessment because
running report_query.sql over the full window takes the better part of an hour. You are
not expected to sit through that, repeatedly, while iterating. You ARE expected to
establish the baseline cost yourself, from measured slices, and to say how you did it.

    # measure a slice instead: copy the query, narrow the date literals, time it
    python3 bench_report.py baseline --db ../data/perf.sqlite \
        --sql one_day.sql --out one_day.json

`check` fails loudly if your result set differs from the reference on any
column the baseline produces. Extra columns you add (e.g. p95_latency_ms) are
carried through and reported, not compared - Task 4 tells you how they are
checked.

You may replace --sql with --module mypkg.report:run if your solution is not a
single statement; the callable takes a sqlite3.Connection and returns a list of
dicts.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sqlite3
import gzip
import statistics
import time

BASELINE_SQL = "report_query.sql"
REFERENCE = "../data/report_reference.json.gz"


def rows_from_sql(con: sqlite3.Connection, sql: str) -> list[dict]:
    con.row_factory = sqlite3.Row
    cur = con.execute(sql)
    return [dict(r) for r in cur.fetchall()]


def rows_from_module(con: sqlite3.Connection, spec: str) -> list[dict]:
    mod_name, _, fn_name = spec.partition(":")
    mod = importlib.import_module(mod_name)
    return list(getattr(mod, fn_name or "run")(con))


def normalise(rows: list[dict], columns: list[str]) -> list[tuple]:
    def cell(v):
        if isinstance(v, float):
            return round(v, 6)
        return v
    return sorted(tuple(cell(r.get(c)) for c in columns) for r in rows)


def run_once(args) -> tuple[list[dict], float]:
    con = sqlite3.connect(args.db)
    t0 = time.perf_counter()
    if args.module:
        rows = rows_from_module(con, args.module)
    else:
        rows = rows_from_sql(con, open(args.sql).read())
    elapsed = time.perf_counter() - t0
    con.close()
    return rows, elapsed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["baseline", "check"])
    ap.add_argument("--db", default="../data/perf.sqlite")
    ap.add_argument("--sql", default=BASELINE_SQL)
    ap.add_argument("--module", help="import path, e.g. report:run")
    ap.add_argument("--baseline", default=REFERENCE,
                    help="reference result; .json or .json.gz")
    ap.add_argument("--budget-s", type=float, default=10.0,
                    help="wall-clock target for the full window")
    ap.add_argument("--out", default="baseline.json")
    ap.add_argument("--repeat", type=int, default=1)
    args = ap.parse_args()

    if args.mode == "baseline":
        rows, elapsed = run_once(args)
        cols = list(rows[0].keys()) if rows else []
        with open(args.out, "w") as fh:
            json.dump({"columns": cols, "elapsed_s": elapsed, "rows": rows}, fh)
        print(f"baseline: {len(rows)} rows in {elapsed:.2f}s -> {args.out}")
        return

    opener = gzip.open if args.baseline.endswith(".gz") else open
    with opener(args.baseline, "rt") as fh:
        ref = json.load(fh)
    ref_cols = ref["columns"]
    ref_norm = normalise(ref["rows"], ref_cols)

    times = []
    rows = []
    for _ in range(args.repeat):
        rows, elapsed = run_once(args)
        times.append(elapsed)

    missing = [c for c in ref_cols if rows and c not in rows[0]]
    if missing:
        raise SystemExit(f"FAIL: result is missing baseline columns: {missing}")
    got_norm = normalise(rows, ref_cols)

    if got_norm != ref_norm:
        # show the first few divergences to make debugging possible
        diff = [(a, b) for a, b in zip(ref_norm, got_norm) if a != b][:5]
        print(f"FAIL: {len(ref_norm)} reference rows vs {len(got_norm)} produced")
        for a, b in diff:
            print("  expected:", a)
            print("  got     :", b)
        raise SystemExit(1)

    extra = [c for c in (rows[0].keys() if rows else []) if c not in ref_cols]
    print(f"OK: {len(rows)} rows match the reference on {len(ref_cols)} columns")
    if extra:
        print(f"    extra columns produced (not compared here): {extra}")
    median = statistics.median(times)
    verdict = "PASS" if median <= args.budget_s else "OVER BUDGET"
    print(f"    budget {args.budget_s:.1f}s -> {verdict} (median {median:.3f}s)")
    print(f"    baseline {ref['elapsed_s']:.2f}s | yours "
          f"min {min(times):.3f}s median {statistics.median(times):.3f}s "
          f"max {max(times):.3f}s over {args.repeat} run(s)")
    print(f"    speedup vs baseline (median): {ref['elapsed_s'] / statistics.median(times):.0f}x")


if __name__ == "__main__":
    main()
