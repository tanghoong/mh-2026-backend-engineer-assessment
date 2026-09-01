#!/usr/bin/env python3
"""Task 4 report entry point for bench_report.py --module.

    cd starter
    python3 bench_report.py check --db ../data/perf.sqlite \
        --module src.perf.report:run --repeat 5 --budget-s 10

The SQL itself is `starter/my_report.sql` and is byte-identical to the baseline on all
13 of its columns, plus p95_latency_ms. This wrapper exists for one reason: a single
connection-level PRAGMA.

`temp_store=MEMORY` keeps SQLite's sort and grouping scratch space in RAM instead of
spilling it to temporary files. The rewrite is sort-bound - a DISTINCT over ~570k rows,
two window partitions and four GROUP BYs - so the spill dominates. Measured on this
machine, it is the difference between roughly 13-21 s and roughly 8.6 s, and it costs
nothing: no schema change, no index, no write amplification on a ledger that already
takes ~40 writes per order line at peak.

Rejected alongside it, and reported in PERF.md §6 because "obvious" is not "measured":

  cache_size=256MB alone              20.8 s   - slower than doing nothing
  cache_size=256MB + temp_store       11.4 s   - slower than temp_store alone
  an expression index on
  (tenant_id, substr(created_at,1,10), item_code)
                                       7.0 s   - faster, but it is a schema change on a
                                                 hot table and a permanent write cost,
                                                 bought to save 1.5 s we do not need
"""
from __future__ import annotations

import pathlib
import sqlite3

SQL_PATH = pathlib.Path(__file__).resolve().parents[2] / "starter" / "my_report.sql"


def run(con: sqlite3.Connection) -> list[dict]:
    """Return the report as a list of dicts, one per output group."""
    con.execute("PRAGMA temp_store=MEMORY")
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(SQL_PATH.read_text(encoding="utf-8"))]
