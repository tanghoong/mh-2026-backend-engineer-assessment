#!/usr/bin/env python3
"""Builds the SQLite database for Task 4 (performance).

Stdlib only. ~1.1M ledger rows, ~20 seconds to build, ~120 MB on disk.

    python3 make_perf_db.py --out ../data/perf.sqlite

Do not commit the .sqlite file - regenerate it. Same seed, same database.

Schema mirrors (in simplified form) the ledger every match attempt writes to
in production: one row per candidate considered, not one row per order line.
"""

import argparse
import os
import random
import sqlite3

DDL = """
PRAGMA journal_mode=OFF;
PRAGMA synchronous=OFF;

CREATE TABLE tenant (
    tenant_id   TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    plan        TEXT NOT NULL
);

CREATE TABLE order_line (
    line_id     TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    channel     TEXT NOT NULL,
    created_at  TEXT NOT NULL,          -- ISO8601 UTC
    raw_text    TEXT NOT NULL
);

-- one row per (line, candidate item) considered by the matcher
CREATE TABLE match_event (
    event_id    INTEGER PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    line_id     TEXT NOT NULL,
    item_code   TEXT NOT NULL,
    stage       TEXT NOT NULL,          -- alias | lexical | dense | rerank
    score       REAL NOT NULL,
    rank        INTEGER NOT NULL,
    accepted    INTEGER NOT NULL,       -- 1 = this candidate became the answer
    latency_ms  INTEGER NOT NULL,
    created_at  TEXT NOT NULL           -- ISO8601 UTC
);

CREATE TABLE item (
    tenant_id   TEXT NOT NULL,
    item_code   TEXT NOT NULL,
    item_name   TEXT NOT NULL,
    item_group  TEXT NOT NULL,
    disabled    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, item_code)
);
"""

STAGES = ["alias", "lexical", "lexical", "dense", "dense", "rerank"]
CHANNELS = ["whatsapp", "email_pdf", "portal_csv", "voice_note"]
GROUPS = ["Fasteners", "Pipes", "Tools", "Safety", "Frozen", "Dairy", "Seafood"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="../data/perf.sqlite")
    ap.add_argument("--seed", type=int, default=20260809)
    ap.add_argument("--lines", type=int, default=120_000)
    args = ap.parse_args()

    if os.path.exists(args.out):
        os.remove(args.out)
    rng = random.Random(args.seed)
    con = sqlite3.connect(args.out)
    con.executescript(DDL)

    tenants = [(f"T{i:03d}", f"Tenant {i:03d}",
                rng.choice(["starter", "growth", "growth", "enterprise"])) for i in range(1, 41)]
    con.executemany("INSERT INTO tenant VALUES (?,?,?)", tenants)

    # skewed tenant volume: top 3 tenants own ~55% of traffic (this matters)
    weights = [40, 30, 22] + [3] * 17 + [1] * 20
    pool = []
    for (tid, _n, _p), w in zip(tenants, weights):
        pool.extend([tid] * w)

    items = []
    for tid, _n, _p in tenants:
        for k in range(1200):
            items.append((tid, f"{tid}-I{k:05d}", f"item {k} for {tid}",
                          rng.choice(GROUPS), 1 if rng.random() < 0.06 else 0))
    con.executemany("INSERT INTO item VALUES (?,?,?,?,?)", items)
    items_by_tenant = {}
    for tid, code, *_ in items:
        items_by_tenant.setdefault(tid, []).append(code)

    def ts(day, sec):
        return f"2026-{(day // 31) + 4:02d}-{(day % 31) + 1:02d}T{sec // 3600:02d}:{(sec % 3600) // 60:02d}:{sec % 60:02d}Z"

    lines, events = [], []
    eid = 0
    for i in range(args.lines):
        tid = rng.choice(pool)
        lid = f"L{i:07d}"
        day = rng.randrange(0, 120)
        created = ts(day, rng.randrange(0, 86400))
        lines.append((lid, tid, f"C{rng.randrange(1, 400):04d}",
                      rng.choice(CHANNELS), created, f"raw line {i}"))
        n_cand = rng.choice([3, 5, 8, 8, 12, 20])
        winner = rng.randrange(n_cand) if rng.random() < 0.72 else -1
        for r in range(n_cand):
            eid += 1
            events.append((eid, tid, lid, rng.choice(items_by_tenant[tid]),
                           rng.choice(STAGES), round(rng.uniform(0.1, 0.99), 4), r,
                           1 if r == winner else 0,
                           int(rng.lognormvariate(4.2, 0.9)), created))
        if len(events) > 200_000:
            con.executemany("INSERT INTO match_event VALUES (?,?,?,?,?,?,?,?,?,?)", events)
            events = []
    con.executemany("INSERT INTO order_line VALUES (?,?,?,?,?,?)", lines)
    con.executemany("INSERT INTO match_event VALUES (?,?,?,?,?,?,?,?,?,?)", events)
    con.commit()

    # NOTE: exactly one index ships with the schema. This is on purpose.
    con.execute("CREATE INDEX idx_match_event_line ON match_event(line_id)")
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM match_event").fetchone()[0]
    print(f"{args.out}: {len(lines)} lines, {n} match events")
    con.close()


if __name__ == "__main__":
    main()
