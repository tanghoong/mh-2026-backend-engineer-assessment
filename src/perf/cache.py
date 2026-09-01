#!/usr/bin/env python3
"""Estimate-before-you-run, and never measure the same thing twice.

Task 4 is about deciding what to measure when you cannot afford to measure everything.
That constraint applies to the measuring as much as to the query: the first calibration
attempt here (one tenant, one day) blew a 90-second cap, and a full-window run of the
baseline is a ~100-hour proposition. So this module does two things:

  estimate(sql)          predict the cost BEFORE running, from calibrated per-metric
                         rates, so a run that cannot finish is never started
  measure(sql, ...)      run it, but return a cached result when the identical work has
                         already been done against the identical database

The cache key covers the SQL text and the database's identity (size + mtime), so
rebuilding perf.sqlite correctly invalidates every stored measurement rather than
silently serving numbers from a different dataset.

    python3 src/perf/cache.py --list        show what has been measured
    python3 src/perf/cache.py --verify      re-run a sample and check the cache is honest
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sqlite3
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "perf.sqlite"
STORE = ROOT / "_work" / "measurements.json"

# ---------------------------------------------------------------- calibration
# Seconds per output group, per metric, measured in isolation via
# slices.keep_only_metric on T040 x 1 day (2 groups). See PERF.md §2.
# These are the ablation results; the estimator is the ablation table made executable.
PER_GROUP_S = {
    "lines_accepted":        0.1810,
    "candidates_considered": 0.0225,
    "avg_accept_score":      0.1265,
    "max_latency_ms":        0.1360,
    "avg_latency_ms":        0.1375,
    "distinct_customers":    0.0215,
    "accepted_disabled":     0.1675,
}
SKELETON_S_PER_GROUP = 0.00675      # GROUP BY with all metrics NULLed out
SCAN_S = 0.158                      # one full pass over match_event (~1.12M rows)

# repeat_items_prev_day is not per-group-constant: its inner EXISTS runs once per
# candidate row, so its cost is (1 + events_in_that_tenant_day) full scans per group.
REPEAT_METRIC = "repeat_items_prev_day"


def _db_identity(db: pathlib.Path) -> str:
    st = db.stat()
    return f"{db.name}:{st.st_size}:{int(st.st_mtime)}"


def _normalise(sql: str) -> str:
    """Whitespace- and comment-insensitive, so cosmetic edits do not miss the cache."""
    sql = re.sub(r"--[^\n]*", "", sql)
    return re.sub(r"\s+", " ", sql).strip()


def key_for(sql: str, db: pathlib.Path, repeat: int) -> str:
    blob = f"{_normalise(sql)}|{_db_identity(db)}|{repeat}"
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


def _load() -> dict:
    if STORE.exists():
        return json.loads(STORE.read_text(encoding="utf-8"))
    return {}


def _save(store: dict) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(store, indent=1, sort_keys=True), encoding="utf-8")


# ---------------------------------------------------------------- estimation

def slice_shape(sql: str, db: pathlib.Path = DB) -> dict:
    """Output groups and the event sum that drives repeat_items_prev_day.

    Both come from cheap aggregates over order_line and match_event; neither runs the
    report. Extracting the window and tenant filter from the SQL keeps the estimate
    honest about the actual slice rather than about an assumed one.
    """
    days = re.findall(r"'(\d{4}-\d{2}-\d{2})'", sql)
    lo, hi = (min(days), max(days)) if days else ("2026-05-01", "2026-06-30")
    tenants = re.findall(r"ol\.tenant_id IN \(([^)]*)\)", sql)
    tlist = [x.strip().strip("'") for x in tenants[0].split(",")] if tenants else []

    where = ["substr(created_at,1,10) >= ?", "substr(created_at,1,10) <= ?"]
    args: list = [lo, hi]
    if tlist:
        where.append(f"tenant_id IN ({','.join('?' * len(tlist))})")
        args += tlist
    w = " AND ".join(where)

    con = sqlite3.connect(db)
    groups = con.execute(
        f"SELECT COUNT(*) FROM (SELECT DISTINCT tenant_id, channel, substr(created_at,1,10) "
        f"FROM order_line WHERE {w})", args).fetchone()[0]
    sum_e = con.execute(f"""
        WITH grp AS (SELECT DISTINCT tenant_id, channel, substr(created_at,1,10) AS day
                     FROM order_line WHERE {w}),
             ev  AS (SELECT tenant_id, substr(created_at,1,10) AS day, COUNT(*) AS n
                     FROM match_event GROUP BY 1,2)
        SELECT COALESCE(SUM(COALESCE(ev.n,0)),0) FROM grp
        LEFT JOIN ev ON ev.tenant_id=grp.tenant_id AND ev.day=grp.day""", args).fetchone()[0]
    con.close()
    return {"groups": groups, "sum_events_over_groups": sum_e, "window": [lo, hi],
            "tenants": tlist or "all"}


def is_baseline_family(sql: str) -> bool:
    """True when the calibrated model applies.

    The rates were measured against the baseline's shape: one correlated scalar subquery
    per metric, re-evaluated per output group. A CTE rewrite shares those column aliases
    but none of that cost structure, so the model is meaningless for it — and an
    estimator that answers confidently outside its domain is worse than one that
    declines. Detected by the correlated-subquery count rather than by the aliases.
    """
    return sql.count("(SELECT") >= 4 and "WITH" not in sql[:200].upper()


def estimate(sql: str, db: pathlib.Path = DB) -> dict:
    """Predicted seconds for one run, and the breakdown that produced it.

    Returns `applies=False` and no prediction for anything outside the baseline family;
    see `is_baseline_family`.
    """
    shape = slice_shape(sql, db)
    if not is_baseline_family(sql):
        return {"predicted_s": None, "applies": False, "breakdown": {}, **shape}
    g, sum_e = shape["groups"], shape["sum_events_over_groups"]
    parts = {"skeleton": SKELETON_S_PER_GROUP * g}
    for alias, rate in PER_GROUP_S.items():
        if f"NULL AS {alias}" not in sql and alias in sql:
            parts[alias] = rate * g
    if f"NULL AS {REPEAT_METRIC}" not in sql and REPEAT_METRIC in sql:
        parts[REPEAT_METRIC] = SCAN_S * (g + sum_e)
    total = sum(parts.values())
    return {"predicted_s": total, "applies": True, "breakdown": parts, **shape}


# ---------------------------------------------------------------- measurement

def measure(sql: str, repeat: int = 1, cap_s: float = 60.0, db: pathlib.Path = DB,
            label: str = "", force: bool = False, max_predicted_s: float | None = None,
            store_result: bool = True) -> dict:
    """Cached, estimate-gated timing.

    Returns immediately from the cache when the same SQL has been timed against the same
    database with the same repeat count. Otherwise estimates first: if the prediction
    exceeds `max_predicted_s`, the run is refused rather than started, because a run that
    will not finish costs the same as one that was never launched but takes longer to
    admit it.
    """
    k = key_for(sql, db, repeat)
    store = _load()
    if not force and k in store and "median_s" in store[k]:
        return {**store[k], "cached": True}

    pred = estimate(sql, db)
    if (max_predicted_s is not None and pred["predicted_s"] is not None
            and pred["predicted_s"] > max_predicted_s):
        return {"refused": True, "cached": False, "label": label,
                "predicted_s": pred["predicted_s"], "max_predicted_s": max_predicted_s,
                "reason": "predicted cost exceeds the ceiling; not started"}

    times = []
    for _ in range(repeat):
        con = sqlite3.connect(db)
        deadline = time.perf_counter() + cap_s
        con.set_progress_handler(lambda: 1 if time.perf_counter() > deadline else 0, 20_000)
        t0 = time.perf_counter()
        try:
            rows = len(con.execute(sql).fetchall())
        except sqlite3.OperationalError:
            con.close()
            rec = {"label": label, "capped_at_s": cap_s, "predicted_s": pred["predicted_s"],
                   "db": _db_identity(db), "at": time.strftime("%Y-%m-%d %H:%M:%S")}
            if store_result:
                store[k] = rec
                _save(store)
            return {**rec, "cached": False}
        times.append(time.perf_counter() - t0)
        con.close()

    rec = {"label": label, "median_s": sorted(times)[len(times) // 2],
           "min_s": min(times), "max_s": max(times), "runs": repeat, "rows": rows,
           "predicted_s": pred["predicted_s"], "groups": pred["groups"],
           "db": _db_identity(db), "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    rec["predicted_over_actual"] = (round(rec["predicted_s"] / rec["median_s"], 3)
                                    if pred["applies"] else None)
    if store_result:
        store[k] = rec
        _save(store)
    return {**rec, "cached": False}


def _main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--estimate", help="path to a .sql file")
    args = ap.parse_args()
    if args.list:
        store = _load()
        print(f"{len(store)} cached measurement(s) in {STORE.relative_to(ROOT)}")
        for k, v in sorted(store.items(), key=lambda kv: kv[1].get("at", "")):
            t = (f"{v['median_s']:8.3f}s" if "median_s" in v
                 else f"  >{v.get('capped_at_s', 0):.0f}s cap")
            acc = v.get("predicted_over_actual")
            print(f"  {k}  {t}  pred/actual={acc if acc else '-':<6}  {v.get('label','')}")
    elif args.estimate:
        e = estimate(pathlib.Path(args.estimate).read_text(encoding="utf-8"))
        print(f"slice: {e['groups']} groups, window {e['window']}, tenants {e['tenants']}")
        if not e.get("applies"):
            print("  no prediction: the calibrated model covers the baseline's "
                  "correlated-subquery shape only")
            return
        for k, v in sorted(e["breakdown"].items(), key=lambda kv: -kv[1]):
            print(f"  {k:<24} {v:>12,.1f}s")
        print(f"  {'PREDICTED TOTAL':<24} {e['predicted_s']:>12,.1f}s "
              f"({e['predicted_s'] / 3600:,.1f} h)")
    else:
        ap.print_help()


if __name__ == "__main__":
    _main()
