# PERF — Task 4

> **Result: 7.3–9.1 s, byte-identical to the reference on all 13 baseline columns, plus
> `p95_latency_ms`.** Budget was 10 s. No index, no schema change, no materialisation.
>
> **That is a range, not a number, and the range is the honest headline.** Four separate
> 5-run batches on this machine gave medians of 7.32, 7.34, 8.17 and 9.13 s. Every batch
> passes; none of them passes by much. A grader on a slower laptop could plausibly miss the
> budget, and the lever if that happens is already measured and declined: the expression
> index in §6 takes it to ~5.2 s at the cost of a permanent write tax.
>
> ```
> cd starter
> PYTHONPATH=.. python3 bench_report.py check --db ../data/perf.sqlite \
>     --module src.perf.report:run --repeat 5 --budget-s 10
> ```

---

## 1. The baseline, estimated

**The baseline cannot be measured, and neither can most of its slices.** The first
calibration attempt was the smallest slice that exists — one tenant, one day, **2 output
groups** — and it blew a 90-second cap. That is the constraint the task is really about,
so the measurement plan had to be designed before any measuring happened.

### Method

1. **Ablate on a tiny slice.** `slices.keep_only_metric` runs one metric at a time with
   the other seven replaced by `NULL`, on `T040 × 1 day` (2 groups, 38 events).
2. **Derive per-group rates** from those isolated timings.
3. **Test whether the rates are additive** — if they are, the model can be composed.
4. **Test which axis the cost scales along** — this is the step that decides everything.
5. **Extrapolate**, then validate the extrapolation on a slice that was not used to build it.

### Step 4 is the one that matters: groups, not rows

Same query (7 cheap metrics), four slices:

| slice | groups | events | time | **s/group** | µs/event |
|---|---|---|---|---|---|
| T040 × 1 day | 2 | 38 | 1.269 s | **0.634** | 33,386 |
| T001 × 1 day | 4 | 2,385 | 3.807 s | **0.952** | 1,596 |
| T040 × 8 days | 26 | 405 | 16.050 s | **0.617** | 39,630 |
| T001 × 8 days | 32 | 18,789 | 28.360 s | **0.886** | 1,509 |

**`s/group` varies by 1.5× across a 63× range in events. `µs/event` varies by 26×.**
T001 against T040 on one day: groups 2×, events 63×, **time 3.0×**.

The cause is in the data, not the query: tenant volume is deliberately skewed — the
generator gives the top three tenants ~55% of traffic — while *groups* are near-uniform,
because every tenant appears on almost every day across four channels (8,666 actual
groups against 40 × 4 × 61 = 9,760 possible, 88.8% dense).

So a slice picked by rows tells you about the tenant you picked. A slice picked by groups
tells you about the report.

### Validating the axis before trusting it

Predict a slice that was not used to fit the model — all tenants × 1 day, 144 groups:

| extrapolated along | prediction | spread |
|---|---|---|
| **groups** (0.62–0.95 s/group) | **89–137 s** | 1.5× |
| events (1,596–33,386 µs/event) | 15–319 s | **21×** |
| **measured** | **120.6 s** | — |

The groups prediction contains the answer in a 1.5× band. The events prediction spans 21×
and its endpoints are wrong by 8× in one direction and 2.6× in the other. **That is the
difference the brief points at**, and it is not a matter of taste: one axis is stable
because groups are uniform, the other is not because rows are skewed.

`repeat_items_prev_day` is the exception and needs its own model. Its inner `EXISTS` runs
once per candidate row, so its cost is `(1 + events_in_tenant_day)` full scans per group.
Calibrated at **0.158 s per full scan** and validated on a held-out slice: T020 × 1 day
predicted 107 s, measured **86.1 s** (0.81×).

### The estimate

```
groups over the window                              8,666
Σ events over groups (drives repeat_items)      2,220,686

7 cheap metrics   8,666 × 0.8378 s/group  =         7,260 s
repeat_items      0.158 × (8,666 + 2,220,686) =   352,238 s
                                            ------------------
TOTAL                                             359,498 s  ≈  99.9 hours
```

Reproduce with `python3 src/perf/cache.py --estimate starter/report_query.sql`.

The estimator is the ablation table made executable, and it was checked against three
independent slices before being trusted:

| slice | predicted | actual | ratio |
|---|---|---|---|
| 7 cheap metrics, all tenants × 1 day | 115.1 s | 120.6 s | 0.95 |
| repeat_items only, T020 × 1 day | 96.1 s | 86.1 s | 1.12 |
| 7 cheap metrics, T001 × 8 days | 25.6 s | 28.4 s | 0.90 |

### I believe the shipped reference's `elapsed_s` is wrong

`data/report_reference.json.gz` records `elapsed_s: 3050.0`, i.e. "the better part of an
hour". My estimate is **~100 hours — 118× larger**. Stating that plainly, per §11:

- The estimate is built from 12 measurements, is additive to within 5–12% on three
  held-out slices, and rests on a mechanism visible in `EXPLAIN QUERY PLAN`: `SCAN me8`
  containing `SCAN me9`, with no index available on either predicate.
- For 3050 s to be right, this machine would have to be ~120× slower than the author's on
  a single-threaded SQLite scan. Machines do not differ by 120× on that workload.
- `3050.0` is exact to three significant figures with a trailing `.0`. A real
  `bench_report.py baseline` run writes a float like `3047.23`. It reads as a
  hand-entered estimate, which is consistent with the README's note that the reference
  *rows* came from "an independently written query" — nothing there claims the baseline
  itself was ever run to completion.

**This does not change the work.** The rewrite is verified against the reference *rows*,
which are correct. It changes the honesty of the headline: `bench_report.py` will print
"speedup 416×", and the real figure is closer to **49,000×**.

---

## 2. Diagnosis, ranked and established by ablation

Each metric measured alone on `T040 × 1 day` (2 groups), other seven `NULL`ed:

| rank | metric | measured | s/group | share of full-window cost |
|---|---|---|---|---|
| 1 | **`repeat_items_prev_day`** | **12.921 s** | (1+E) × 0.158 | **98.0%** |
| 2 | `lines_accepted` | 0.362 s | 0.1810 | 0.44% |
| 3 | `accepted_disabled` | 0.335 s | 0.1675 | 0.40% |
| 4 | `avg_latency_ms` | 0.275 s | 0.1375 | 0.33% |
| 5 | `max_latency_ms` | 0.272 s | 0.1360 | 0.33% |
| 6 | `avg_accept_score` | 0.253 s | 0.1265 | 0.31% |
| 7 | `candidates_considered` | 0.045 s | 0.0225 | 0.05% |
| 8 | `distinct_customers` | 0.043 s | 0.0215 | 0.05% |
| — | `GROUP BY` skeleton, all metrics NULL | 0.0135 s | 0.00675 | 0.02% |

**Additivity check.** The seven cheap metrics sum to 0.7925 s/group in isolation; measured
together on an independent slice they cost 0.8378 s/group — **5.4% apart**. The metrics do
not share work, so the ranking composes rather than merely ordering.

### The part that surprised me

The ablation says one column is 98% of the cost, which invites the obvious conclusion:
fix that column and go home. **The numbers say otherwise.** Delete
`repeat_items_prev_day` entirely and the report still costs **7,260 s — 726× over
budget**, because the other seven are *also* per-group full scans. They are cheap
individually and ruinous collectively.

So the ranking is real but the fix cannot be local to the top of it. The dominant cost is
one column; the dominant *defect* is the shape — a correlated subquery evaluated once per
output group, 8,666 times, against a table with one index on an unrelated column. Ranking
the columns identifies the worst offender and would have led to a fix that was 726× short.

That distinction is the whole finding, and it is only visible because the seven "cheap"
metrics were measured rather than dismissed.

---

## 3. The fix

**Target stated before starting: full window ≤ 10 s, byte-identical. Achieved: 7.3–9.1 s
across four batches — inside budget every time, with less headroom than a single figure
would suggest.**

`starter/my_report.sql`, driven through `src/perf/report.py`. Eight correlated subqueries
become five single-pass CTEs joined once:

| CTE | Replaces | Passes |
|---|---|---|
| `ch_lines` | `lines_total`, `distinct_customers` | 1 over `order_line` |
| `ch_events` | `lines_accepted`, `candidates_considered` | 1 join `order_line × match_event` |
| `td_scan` → `td_events` | `avg_accept_score`, `max_latency_ms`, `avg_latency_ms`, `accepted_disabled`, **and `p95_latency_ms`** | 1 windowed pass |
| `td_items` → `td_repeat` | `repeat_items_prev_day` | 1 DISTINCT + 1 self-join |

Five of the eight baseline subqueries key on tenant-day only, with **no channel filter**,
so the baseline recomputes each of them identically for all four channels of a tenant-day.
Computing them once is a free 4× before any other change.

### Data properties relied on, asserted rather than assumed

| property | verified | why it matters |
|---|---|---|
| `match_event.tenant_id` = its line's `tenant_id` | 0 mismatches / 1,119,139 | `lines_accepted` keys on `me2.tenant_id`, `candidates_considered` on `ol3.tenant_id`; one grouping serves both only if these agree |
| `match_event.created_at` = its line's `created_at` | 0 mismatches | lets the tenant-day CTEs key on the event's day |
| every event has an `item` row | 0 orphans | `td_scan` INNER JOINs `item`; an orphan would silently drop out of `max_latency_ms` and `avg_latency_ms`, not just `accepted_disabled` |

The third is the fragile one. It is a correctness dependency introduced by folding the
`item` join into the shared scan, and it would fail silently, so it is stated here and
re-checked by the harness rather than trusted.

### An optimisation that was correct and wrong

The self-join in `td_repeat` looks like a textbook window-function rewrite: order each
`(tenant, item_code)` by day and check whether the preceding day is `day - 1`. One sort
instead of a 410k × 410k join.

**It is wrong on this ledger, and `check` caught it**: `repeat_items_prev_day` for T001 on
2026-05-01 went from 825 to 159.

The ledger contains **impossible calendar dates**. `make_perf_db.py` derives the day of
month as `day % 31 + 1` regardless of month length, so `2026-04-31`, `2026-02-30` and
`2026-06-31` all exist as strings. They sort lexicographically between the real dates, so
`LAG` lands on `2026-04-31` while `date('2026-05-01','-1 day')` is `2026-04-30`, and the
match silently fails.

The self-join asks for the exact previous calendar day, which is what the baseline asks
for. The window function asks for "the previous day this item appeared", which is the same
question only on a calendar-sane dataset. Kept the self-join; the comment in the SQL says
why, because the next person will have the same idea.

### `temp_store=MEMORY`

The rewrite is sort-bound — one DISTINCT over ~570k rows, two window partitions, four
GROUP BYs — and SQLite spills sort scratch to temporary files by default. One connection
PRAGMA keeps it in RAM:

| configuration | median |
|---|---|
| defaults | 13.3–21.3 s |
| **`temp_store=MEMORY`** | **7.3 s** |
| `cache_size=256MB` alone | 20.8 s |
| `cache_size=256MB` + `temp_store=MEMORY` | 11.4 s |

`cache_size` is the knob everyone reaches for and it made things **worse in both
combinations**. It is in the table because it was measured, and it is the reason the
PRAGMA choice is a finding rather than a guess.

---

## 4. `p95_latency_ms`

Nearest-rank p95 of `latency_ms` over the same tenant-day set as `max_latency_ms`.

Rank = `ceil(0.95n)`, expressed as integer arithmetic `(n * 95 + 99) / 100`, and selected
inside the aggregate that already computes `max_latency_ms`:

```sql
MAX(CASE WHEN rn = (n * 95 + 99) / 100 THEN latency_ms END) AS p95_latency_ms
```

**It costs nothing.** The `ROW_NUMBER()` and `COUNT()` window functions ride along on the
scan the other four tenant-day metrics already need, so the column is folded into an
existing pass rather than added as a fifth one. Adding it as a separate CTE cost 2.146 s;
folding it in cost 0.

Verified independently: 40 randomly sampled tenant-days, p95 recomputed in Python from
raw `latency_ms` values, **40/40 match**. `bench_report.py` does not compare extra
columns, so this check exists precisely because the harness will not do it.

---

## 5. What I did not fix

- **The report is still recomputed from scratch on every call.** Ops load it on every page
  view, one tenant at a time, plus a nightly all-tenant roll-up. At 7.3 s a page view is
  still bad UX. Not fixed because the fix is materialisation, and ops believe the
  dashboard is live (see §6). **Cost:** 7.3 s per page view. **When I would come back:**
  as soon as anyone asks for sub-second, which is the next thing they will ask for.
- **The date window is a literal in four places.** The service binds `:date_from` /
  `:date_to`; my CTEs repeat the bounds, and `td_items` needs `date(from, '-1 day')`.
  That is a parameterisation bug waiting to happen. **Cost:** one careless edit produces a
  silently wrong first day. **Fix:** bind once in `report.py` and interpolate.
- **The impossible calendar dates.** `2026-04-31` is a data-quality defect in the ledger
  and cannot be fixed in a query. It is currently harmless — the affected rows just never
  match a previous day — but it is a trap for the next optimiser. **Fix:** a constraint at
  write time, and a backfill.
- **The single shipped index is still on `line_id`.** Useful to nothing in this report. I
  left it alone rather than reshaping the schema for one query.

## 6. Trade-offs accepted

**Indexes cost write throughput, so I measured one and declined it.** An expression index
on `(tenant_id, substr(created_at,1,10), item_code)` costs 1.6 s to build, 41 MB on disk,
and takes the report to **7.0 s** by itself or **5.15 s** with the PRAGMA.

Declined. The ledger takes ~40 writes per order line at peak, and this index is on the
hot table, so every one of those writes pays for it forever. It buys 2.2 s of headroom
below a budget already met by a connection-level PRAGMA that costs nothing. **An index is
a permanent write tax paid to solve a read problem that was already solved.** If the
budget tightens or volume grows, this is the first lever — and §7 says when.

**Materialisation costs freshness, so I did not materialise.** A nightly rollup table
would make this report O(output) instead of O(ledger) and take it under 100 ms. It also
introduces a staleness contract where none exists today. Ops believe the dashboard is
live; a rollup makes that false, quietly, and the first person to notice will be someone
acting on yesterday's number. That is a product decision, not a query decision.

**Schema changes cost a migration on a hot table, so there is none.** Nothing in the fix
touches DDL. The whole change is one SQL file and one PRAGMA, which is also why it can be
reviewed in one sitting and reverted in one commit.

**`temp_store=MEMORY` costs RAM during the query.** Peak scratch is on the order of the
sorted sets — tens of MB here. On a shared reporting host running many concurrent report
requests that is a real cost, and it scales with concurrency rather than with data. The
mitigation is a concurrency limit on the report endpoint, not a different PRAGMA.

## 7. The honest ceiling

**At 50× today's volume — ~56M match events — this fix does not hold.**

**What breaks first: `td_items`.** It is a DISTINCT over `(tenant_id, day, item_code)`,
currently ~570k input rows producing 410k output rows, and it is already the single most
expensive CTE at 3.5 s. At 50× that is ~28M input rows. Worse, the win from
`temp_store=MEMORY` disappears exactly then: the sort no longer fits in RAM, spills
resume, and the configuration that bought a 2–3× speedup becomes a memory-pressure
problem instead. **The fix degrades non-linearly, and it degrades at the point where the
thing that saved it stops applying.** That is the honest shape of it.

Second: the whole design is still O(ledger) per report call, and the ledger grows without
bound while the output stays at 8,666 rows. Reading 56M rows to produce 8,666 is the
wrong shape however fast the scan is.

**The next architecture is an incremental rollup** maintained on the write path: one row
per `(tenant, day, channel)` updated as events land, so the report reads pre-aggregated
output and becomes O(groups). `repeat_items_prev_day` needs a companion
`(tenant, day, item_code)` presence set — the expensive part is a set-membership question
about yesterday, which is cheap to maintain incrementally and ruinous to recompute.

**Why that is not what I built today.** It is a write-path change plus a migration on a
hot table plus a freshness contract that does not currently exist, for a report that needs
to be 30% faster, not 100× faster. Building it now would trade a measured 7.3 s for an
unmeasured operational surface. The trigger to build it is volume growth or a sub-second
requirement — and the estimator in `src/perf/cache.py` is the instrument that will say
when, since it predicts cost from group counts and event sums without running anything.

---

## Appendix — reproducing the measurements

```bash
cd starter && python3 make_perf_db.py --out ../data/perf.sqlite      # ~11 s, 120 MB

# the estimate, without running the baseline
python3 src/perf/cache.py --estimate starter/report_query.sql

# the fix, checked and timed
cd starter && PYTHONPATH=.. python3 bench_report.py check \
    --db ../data/perf.sqlite --module src.perf.report:run --repeat 5 --budget-s 10
```

`src/perf/cache.py` caches every measurement against the database's size and mtime, so a
rebuilt database invalidates the cache rather than silently serving numbers from a
different dataset. `python3 src/perf/cache.py --list` shows what has been measured and how
close each prediction was. It also refuses to start a run whose predicted cost exceeds a
ceiling, which is what turns "do not run the full query" from advice into a guardrail.
