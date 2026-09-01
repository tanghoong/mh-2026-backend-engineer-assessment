#!/usr/bin/env python3
"""Time a SQL variant against perf.sqlite. Read-only, stdlib.

Every measurement carries a hard wall-clock cap. The task is about deciding what to
measure when you cannot afford to measure everything, and an unbounded timing run is
exactly the thing that makes that decision for you by accident.
"""
from __future__ import annotations

import pathlib
import sqlite3
import statistics
import time

DB = pathlib.Path(__file__).resolve().parents[2] / "data" / "perf.sqlite"


class Budget(Exception):
    """A measurement exceeded its cap and was abandoned rather than waited out."""


def _progress_guard(deadline: float):
    """SQLite progress handler: abort the statement once the deadline passes."""
    def handler():
        return 1 if time.perf_counter() > deadline else 0
    return handler


def time_sql(sql: str, repeat: int = 1, cap_s: float = 60.0,
             db: pathlib.Path | None = None) -> dict:
    """Run `sql` `repeat` times, return timing plus the row count.

    Raises Budget if any single run exceeds cap_s, so a mis-sized slice costs the cap
    rather than however long it would have taken.
    """
    times, rows = [], 0
    for _ in range(repeat):
        con = sqlite3.connect(db or DB)
        con.set_progress_handler(_progress_guard(time.perf_counter() + cap_s), 20_000)
        t0 = time.perf_counter()
        try:
            rows = len(con.execute(sql).fetchall())
        except sqlite3.OperationalError as exc:
            con.close()
            raise Budget(f"exceeded {cap_s:.0f}s cap ({exc})") from exc
        times.append(time.perf_counter() - t0)
        con.close()
    return {"median_s": statistics.median(times), "min_s": min(times),
            "max_s": max(times), "rows": rows, "runs": repeat}


def group_count(day_from: str, day_to: str, tenants: list[str] | None = None,
                db: pathlib.Path | None = None) -> int:
    """Output groups for a slice, without running the report.

    Cheap: it touches only order_line, not the correlated subqueries. Used to test
    whether cost tracks groups rather than rows.
    """
    where = ["substr(created_at,1,10) >= ?", "substr(created_at,1,10) <= ?"]
    args: list = [day_from, day_to]
    if tenants:
        where.append(f"tenant_id IN ({','.join('?' * len(tenants))})")
        args += tenants
    sql = ("SELECT COUNT(*) FROM (SELECT DISTINCT tenant_id, channel, "
           "substr(created_at,1,10) FROM order_line WHERE " + " AND ".join(where) + ")")
    con = sqlite3.connect(db or DB)
    n = con.execute(sql, args).fetchone()[0]
    con.close()
    return n


def row_count(day_from: str, day_to: str, tenants: list[str] | None = None,
              db: pathlib.Path | None = None) -> dict:
    """Order lines and match events inside a slice. Also cheap."""
    where = ["substr(ol.created_at,1,10) >= ?", "substr(ol.created_at,1,10) <= ?"]
    args: list = [day_from, day_to]
    if tenants:
        where.append(f"ol.tenant_id IN ({','.join('?' * len(tenants))})")
        args += tenants
    w = " AND ".join(where)
    con = sqlite3.connect(db or DB)
    lines = con.execute(f"SELECT COUNT(*) FROM order_line ol WHERE {w}", args).fetchone()[0]
    events = con.execute(
        f"SELECT COUNT(*) FROM match_event me JOIN order_line ol ON ol.line_id = me.line_id "
        f"WHERE {w}", args).fetchone()[0]
    con.close()
    return {"lines": lines, "events": events}
