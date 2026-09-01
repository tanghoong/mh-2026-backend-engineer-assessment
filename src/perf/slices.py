#!/usr/bin/env python3
"""Generate measurable slices and ablations of the Task 4 baseline query.

Read-only with respect to `starter/report_query.sql` — variants are produced in memory
or written to new files; the baseline is never edited.

Three transformations, composable:

  narrow(sql, day_from, day_to)   restrict the outer date window
  only_tenants(sql, [...])        restrict the outer query to named tenants
  drop_metric(sql, alias)         replace one metric's correlated subquery with NULL

`drop_metric` is the ablation instrument (§7.2: "remove one metric at a time and
re-measure"). It keeps the column in the SELECT list so the shape of the result is
unchanged and only that metric's cost disappears.
"""
from __future__ import annotations

import pathlib
import re

BASELINE = pathlib.Path(__file__).resolve().parents[2] / "starter" / "report_query.sql"

# The eight correlated subqueries, in the order they appear.
METRICS = [
    "lines_accepted",
    "candidates_considered",
    "avg_accept_score",
    "max_latency_ms",
    "avg_latency_ms",
    "distinct_customers",
    "repeat_items_prev_day",
    "accepted_disabled",
]


def baseline_sql() -> str:
    return BASELINE.read_text(encoding="utf-8")


def narrow(sql: str, day_from: str, day_to: str) -> str:
    """Restrict the outer date window. The correlated subqueries are untouched —
    that asymmetry is the point of the whole task."""
    sql = sql.replace("'2026-05-01'", f"'{day_from}'")
    sql = sql.replace("'2026-06-30'", f"'{day_to}'")
    return sql


def only_tenants(sql: str, tenants: list[str]) -> str:
    """Add a tenant restriction to the OUTER query only."""
    ids = ", ".join(f"'{t}'" for t in tenants)
    return sql.replace(
        "WHERE substr(ol.created_at, 1, 10) >=",
        f"WHERE ol.tenant_id IN ({ids})\n  AND substr(ol.created_at, 1, 10) >=",
    )


def _matching_open_paren(sql: str, close_idx: int) -> int:
    """Index of the '(' matching the ')' at close_idx."""
    depth = 0
    for i in range(close_idx, -1, -1):
        if sql[i] == ")":
            depth += 1
        elif sql[i] == "(":
            depth -= 1
            if depth == 0:
                return i
    raise ValueError("unbalanced parentheses")


def drop_metric(sql: str, alias: str) -> str:
    """Replace `( SELECT ... ) AS alias` with `NULL AS alias`.

    The column survives so the result shape does not change; only the work vanishes.
    """
    m = re.search(rf"\bAS\s+{re.escape(alias)}\b", sql)
    if not m:
        raise KeyError(f"no column aliased {alias!r}")
    close = sql.rfind(")", 0, m.start())
    open_ = _matching_open_paren(sql, close)
    return sql[:open_] + f"NULL AS {alias}" + sql[m.end():]


def keep_only_metric(sql: str, alias: str) -> str:
    """Drop every metric except one. Isolates a single subquery's cost."""
    for other in METRICS:
        if other != alias:
            sql = drop_metric(sql, other)
    return sql


if __name__ == "__main__":  # smoke test
    sql = baseline_sql()
    for alias in METRICS:
        assert f"NULL AS {alias}" in drop_metric(sql, alias), alias
    assert "T001" in only_tenants(sql, ["T001"])
    assert "'2026-05-02'" in narrow(sql, "2026-05-01", "2026-05-02")
    print(f"ok: {len(METRICS)} metrics droppable, slicing and tenant filters build")
