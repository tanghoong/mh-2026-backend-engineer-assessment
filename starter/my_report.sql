-- Task 4 rewrite: "Tenant Match Health", byte-identical to report_query.sql,
-- plus the p95_latency_ms column the report owner asked for.
--
--   python3 bench_report.py check --db ../data/perf.sqlite --sql my_report.sql --repeat 5
--
-- The baseline computes eight correlated scalar subqueries once per output group, and
-- match_event carries only idx_match_event_line, so none of their predicates
-- (tenant_id, substr(created_at,1,10)) is indexable. Every subquery is therefore a full
-- scan of ~1.12M rows, repeated 8,666 times. repeat_items_prev_day is worse again: its
-- inner EXISTS runs per candidate row, making it O(events_in_tenant_day x table).
-- Measured contribution: ~98% of total cost. See PERF.md §2.
--
-- The rewrite replaces "once per group" with "once", full stop. Each CTE below is a
-- single pass; the final SELECT is a join between them.
--
-- Two properties of the data are relied on and are asserted in PERF.md §3 rather than
-- assumed: match_event.tenant_id always equals its order_line's tenant_id (0 mismatches
-- in 1,119,139 rows), and match_event.created_at always equals its order_line's
-- created_at (0 mismatches). Both let one grouping serve subqueries that key on
-- different aliases of the same value.

WITH

-- Order lines inside the reporting window. One pass.
ol_win AS (
    SELECT line_id,
           tenant_id,
           customer_id,
           channel,
           substr(created_at, 1, 10) AS day
    FROM order_line
    WHERE substr(created_at, 1, 10) >= '2026-05-01'
      AND substr(created_at, 1, 10) <= '2026-06-30'
),

-- Channel-scoped, from order_line alone: lines_total, distinct_customers.
ch_lines AS (
    SELECT tenant_id,
           channel,
           day,
           COUNT(DISTINCT line_id)     AS lines_total,
           COUNT(DISTINCT customer_id) AS distinct_customers
    FROM ol_win
    GROUP BY tenant_id, channel, day
),

-- Channel-scoped, needing events: lines_accepted, candidates_considered.
-- The baseline keys lines_accepted on me2.tenant_id and candidates_considered on
-- ol3.tenant_id; those are the same value (see header), so one grouping serves both.
ch_events AS (
    SELECT o.tenant_id,
           o.channel,
           o.day,
           COUNT(DISTINCT CASE WHEN me.accepted = 1 THEN me.line_id END) AS lines_accepted,
           COUNT(*)                                                      AS candidates_considered
    FROM ol_win o
    JOIN match_event me ON me.line_id = o.line_id
    GROUP BY o.tenant_id, o.channel, o.day
),

-- Tenant-day scoped, no channel filter in the baseline: avg_accept_score,
-- max_latency_ms, avg_latency_ms, accepted_disabled. The baseline recomputes each of
-- these identically for all four channels of a tenant-day; here they are computed once.
td_scan AS (
    SELECT me.tenant_id,
           substr(me.created_at, 1, 10) AS day,
           me.accepted,
           me.score,
           me.latency_ms,
           it.disabled,
           ROW_NUMBER() OVER (PARTITION BY me.tenant_id, substr(me.created_at, 1, 10)
                              ORDER BY me.latency_ms) AS rn,
           COUNT(*)     OVER (PARTITION BY me.tenant_id, substr(me.created_at, 1, 10)) AS n
    FROM match_event me
    JOIN item it ON it.tenant_id = me.tenant_id AND it.item_code = me.item_code
    WHERE substr(me.created_at, 1, 10) >= '2026-05-01'
      AND substr(me.created_at, 1, 10) <= '2026-06-30'
),
td_events AS (
    SELECT tenant_id,
           day,
           AVG(CASE WHEN accepted = 1 THEN score END)                      AS avg_accept_score,
           MAX(latency_ms)                                                 AS max_latency_ms,
           AVG(latency_ms)                                                 AS avg_latency_ms,
           SUM(CASE WHEN accepted = 1 AND disabled = 1 THEN 1 ELSE 0 END)   AS accepted_disabled,
           -- p95, nearest rank = ceil(0.95n), as integer arithmetic (95n + 99) / 100.
           -- Folded into this aggregate so the window is scanned once, not twice.
           MAX(CASE WHEN rn = (n * 95 + 99) / 100 THEN latency_ms END)      AS p95_latency_ms
    FROM td_scan
    GROUP BY tenant_id, day
),

-- repeat_items_prev_day: distinct item_codes a tenant considered on both `day` and the
-- day before. The baseline expresses this as a per-row EXISTS, which is what made the
-- report unusable; as a set it is one DISTINCT pass and a self-join.
--
-- Deliberately NOT restricted to the window: the previous day of 2026-05-01 is
-- 2026-04-30, which sits outside it. Filtering this CTE to the window would silently
-- zero the first day of the report.
td_items AS (
    SELECT DISTINCT tenant_id,
                    substr(created_at, 1, 10) AS day,
                    item_code
    FROM match_event
    -- 2026-04-30 is the previous day of the window's first day and must be present.
    -- Everything earlier is unreachable by the EXISTS, so it is 58 days of dead weight.
    WHERE substr(created_at, 1, 10) >= '2026-04-30'
      AND substr(created_at, 1, 10) <= '2026-06-30'
),
td_repeat AS (
    -- Self-join, not LAG. A window function taking "the previous day this item appeared"
    -- is the obvious rewrite and it is WRONG on this ledger: the data contains impossible
    -- calendar dates (2026-04-31, 2026-02-30, ...), because the generator derives the day
    -- of month as day%31+1 regardless of month length. Those sort lexicographically
    -- between the real ones, so LAG lands on 2026-04-31 where date('2026-05-01','-1 day')
    -- is 2026-04-30, and the count silently drops (825 -> 159 for T001 on 2026-05-01).
    -- The join asks for the exact previous calendar day, which is what the baseline asks.
    SELECT a.tenant_id,
           a.day,
           COUNT(*) AS repeat_items_prev_day
    FROM td_items a
    JOIN td_items b
      ON b.tenant_id = a.tenant_id
     AND b.item_code = a.item_code
     AND b.day       = date(a.day, '-1 day')
    WHERE a.day >= '2026-05-01'
      AND a.day <= '2026-06-30'
    GROUP BY a.tenant_id, a.day
)

SELECT
    t.tenant_id,
    t.plan,
    cl.channel,
    cl.day,
    cl.lines_total,
    COALESCE(ce.lines_accepted, 0)          AS lines_accepted,
    COALESCE(ce.candidates_considered, 0)   AS candidates_considered,
    te.avg_accept_score,
    te.max_latency_ms,
    te.avg_latency_ms,
    cl.distinct_customers,
    COALESCE(tr.repeat_items_prev_day, 0)   AS repeat_items_prev_day,
    COALESCE(te.accepted_disabled, 0)       AS accepted_disabled,
    te.p95_latency_ms
FROM ch_lines cl
JOIN      tenant   t  ON t.tenant_id  = cl.tenant_id
LEFT JOIN ch_events ce ON ce.tenant_id = cl.tenant_id AND ce.channel = cl.channel
                      AND ce.day       = cl.day
LEFT JOIN td_events te ON te.tenant_id = cl.tenant_id AND te.day = cl.day
LEFT JOIN td_repeat tr ON tr.tenant_id = cl.tenant_id AND tr.day = cl.day
ORDER BY t.tenant_id, cl.channel, cl.day;
