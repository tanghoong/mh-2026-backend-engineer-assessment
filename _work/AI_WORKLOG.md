# AI Work Log — Mindhive Backend Assessment 2026.1

Purpose: an honest, timestamped record of how this repository was worked on with an AI
coding agent (Claude Code / Opus 5). Kept per §11 "Attribute your tools" of the brief.
This is **not** `DECISIONS.md` — no design rationale here, only what was asked, what was
run, and what changed. Design reasoning lives in `DECISIONS.md`.

Timezone: **UTC+08:00** (Asia/Kuala_Lumpur–Singapore). Format: `YYYY-MM-DD HH:MM`.

Legend for **Files touched**: `read` = inspected only · `new` = created · `edit` = modified.

---

## Session 01 — Recon & ground rules

| | |
|---|---|
| **Start** | 2026-09-01 14:37 |
| **End**   | 2026-09-01 14:45 |
| **Duration** | ~8 min |
| **Agent** | Claude Code, Opus 5 (1M context) |
| **Repo state at start** | commit `e7ab5fd inception`, working tree clean |

**Asked for**
1. Create this work log (timestamps, start/end, what was asked and done).
2. Safety audit of the repo — anything destructive, malicious, or resource-heavy.
3. Whether Docker is needed to do the assessment.
4. Read `README.md` and explain the goal, what is tested, and what counts as an
   acceptable result (explained in Chinese).
5. Advice on whether to write solution docs in this repo or a separate one.

**Done**
- Enumerated the tree (15 files, 1.3 MB), read `README.md` in full.
- Read all 5 starter sources: `make_perf_db.py`, `bench_report.py`, `report_query.sql`,
  `sync/fake_erp.py`, `sync/sync_adapter.py`, `sync/run_sync.py`.
- Grepped every `.py`/`.sql` for `subprocess`, `os.system`, `socket`, `urllib`,
  `requests`, `eval`, `exec`, `pickle`, `rmtree`, `remove`. One hit only:
  `make_perf_db.py:75` `os.remove(args.out)` — deletes its own output DB before rebuild.
- Checked toolchain: Python **3.12.10** present via the `py` launcher only
  (`python` / `python3` are **not** on PATH); Docker 29.2.1 present but not required.
- Checked headroom: 191 GB free on `C:` — the Task 4 database needs ~120 MB.
- **No files in `data/` or `starter/` were modified.**

**Files touched**
- `read` — `README.md`, `.gitignore`, `starter/**`, `data/*.csv` (headers only)
- `new`  — `_work/AI_WORKLOG.md` (this file)

**Findings carried forward**
- Repo is inert: stdlib-only, no network, no shell-out, no install step.
- Only cost centres are `make_perf_db.py` (~20 s, ~120 MB) and the unmodified
  `report_query.sql` over the full window (~1 hour) — the brief explicitly says do not
  run the latter.
- Because `python3` is not on PATH, every documented command needs `py -3` locally; the
  submitted `README.md` must still document `python3` for the grader's clean machine.

**Open / next**
- Decide the docs layout (same repo vs. separate) before any file is written.
- Task 1 `DESIGN.md` is the intended starting point.

---

## Session 02 — Scaffolding, trap verification, planning docs

| | |
|---|---|
| **Start** | 2026-09-01 14:50 |
| **End**   | 2026-09-01 15:20 |
| **Duration** | ~30 min |
| **Agent** | Claude Code, Opus 5 (1M context) |
| **Repo state at start** | commit `e7ab5fd`, clean |

**Asked for**
1. Preserve the brief, commit the current state, then begin Task 1 `DESIGN.md`.
2. A to-do / milestone document that another session or another person can resume from.
3. For each trap: define the problem and prove it is real **before** proposing a solution.
4. Time estimates per task, and a scoping pass so nothing is built beyond what is graded.
5. A question bank for the walkthrough — **questions only**, no answers yet.
6. A test strategy defined as purpose → acceptable asset → rerunnable acceptance check.

**Done**
- `README.md` → `ASSESSMENT_BRIEF.md` (verbatim); new `README.md` stub; `_work/` created.
- Commit `7d44c91`.
- Wrote four probe scripts and ran them read-only over `data/`. Results in
  `_work/TRAPS.md`; scripts kept in `_work/probes/` so every number is rerunnable.
- **9 traps CONFIRMED, 1 REFUTED, 3 deferred.** Two of the confirmed ones are not in the
  brief at all: TR-01 (alias table points at superseded `*-OLD` codes — alias-exact
  precision measures **35.9%**, not the ~100% the lane's name implies) and TR-06 (barcodes
  collide **22x** within acme, **16x** within nordic). TR-02 follows from TR-01: the
  `confidence` column is anti-correlated with correctness (1.0 → 22.6%, 0.55 → 100%).
- TR-09 (buyer SKUs resembling another tenant's codes) **refuted** on exact match, 0/776.
  Kept in the register with the control retained anyway — the asymmetry justifies it.
- Wrote `_work/TODO.md` (phases, estimates, scoping, handoff state),
  `_work/TESTING.md` (four test tiers incl. document tests), `_work/QUESTIONS.md`.
- Task 1 `DESIGN.md` **not started** — blocked on OD-1, the operating point, which is a
  human decision (`TODO.md` §5).

**Files touched**
- `new`  — `_work/TODO.md`, `_work/TRAPS.md`, `_work/TESTING.md`, `_work/QUESTIONS.md`,
  `_work/probes/*` (4 scripts + README), `README.md` (stub)
- `edit` — `_work/AI_WORKLOG.md`
- `move` — `README.md` → `ASSESSMENT_BRIEF.md`, unmodified
- **`data/` and `starter/` still untouched.**

**Findings carried forward**
- The intuitive lane ordering (alias exact = most trusted) is **inverted** on this data.
  Supersession resolution has to sit downstream of every lane, not inside the alias lane.
- Nordic is ~89% twin items separated only by a pack-size token, so size arbitration is
  the dominant design concern for that tenant, not general text similarity.
- `source=manual_import` looks diagnostic (10.9% vs 100%) but is a confound with `-OLD`.
  Shipping that gate would be correct-for-the-wrong-reason and would break on the holdout.
- Task 4 reference records `elapsed_s = 3050` (~51 min) → the 10 s budget needs ~305x.

**Open / next**
- OD-1 operating point, OD-2 semantic lane yes/no, OD-3 whether `_work/` ships.
- Then P1 (`DESIGN.md`), then P2 (eval harness before the matcher).

---

## Session 03 — Task 1 design

| | |
|---|---|
| **Start** | 2026-09-01 15:20 |
| **End**   | 2026-09-01 16:20 |
| **Duration** | ~60 min |
| **Agent** | Claude Code, Opus 5 (1M context) |
| **Repo state at start** | commit `eb1ba37`, clean |

**Asked for**
1. Long-running steps flagged; task-to-task dependencies stated; per-task estimates.
2. Whether any API key or authentication is needed.
3. Proceed with Task 1 `DESIGN.md`.

**Done**
- Answered the three open decisions (OD-1/2/3): precision floor + net-value maximisation;
  no semantic lane for now; `_work/` ships with the submission.
- **API keys: none, confirmed.** No `urllib`/`requests`/`socket`/`http` anywhere in the
  repo; the brief bans inference-time network calls outright. Declining the semantic lane
  removed the only component that would have needed a download.
- Flagged the one genuinely long-running item: the unmodified `report_query.sql` over the
  full window (~51 min, recorded in the reference file). Also flagged the hidden cost in
  Task 4 — ablation over 8 metrics on a full-day slice would be 20+ min of pure waiting, so
  the plan uses a small tenant-day slice for ranking and a large one only to confirm.
- Mapped dependencies: **Tasks 4 and 5 sit off the critical path** and can be done in any
  isolated block; critical path is T1 -> T3 harness -> T2 -> T3 analysis -> ship, ~11.5 h.
- New probe `p05_objective.py` derives the operating point rather than asserting it:
  **break-even precision `p* = 92.68 %`** at 20x; **57.14 %** at 3x. At n~250 auto decisions
  the one-sided 95 % lower bound on a 95 % floor is **92.2 %**, below break-even — which is
  the actual argument for setting the floor at 98 % rather than at break-even.
- Wrote `DESIGN.md` (1,510 words against a ~1,500 limit) and `DECISIONS.md` D-01..D-09.

**Files touched**
- `new`  — `DESIGN.md`, `DECISIONS.md`, `_work/probes/p05_objective.py`
- `edit` — `_work/TODO.md` (P1 closed, OD-1/2/3 answered), `_work/AI_WORKLOG.md`
- **`data/` and `starter/` still untouched.**

**Findings carried forward**
- The naive alias lane is worth **-32,340 operator-seconds** on the 64 train lines that
  reach it — *worse than not having the alias table at all* (abstaining on all 64 scores
  -2,560). After the supersession redirect the same 64 lines are worth **+1,280**.
- D-01, D-02, D-05 and D-06 each carry a reversal trigger that later phases must actually
  check. D-05's is the important one: if `source` still predicts after the supersession fix,
  it is real signal; if not, it was a confound and the gate must stay unshipped.

**Open / next**
- P2, the eval harness — before the matcher, per D-08.

---

## Session 04 — Task 5 end to end

| | |
|---|---|
| **Start** | 2026-09-01 16:20 |
| **End**   | 2026-09-01 18:05 |
| **Duration** | ~1 h 45 m |
| **Agent** | Claude Code, Opus 5 (1M context) |
| **Repo state at start** | commit `1bae802`, clean |

**Asked for**
1. Confirm the "do the unblocked work first" ordering.
2. Maintain a decision record for everything, and add a record of how the human directs
   the work — the interview grades whose reasoning it is.
3. Walk through the 7 defect invariants **before** any long block of work.

**Done**
- Reordered the plan by **binary vs degrades-gracefully** rather than by dependency alone.
  The human's ordering was adopted; the justification was replaced (`TODO.md` §2).
- Reproduced all three ticket symptoms deterministically, then proved each mechanism.
  **7 defects for 3 tickets** — 4 are latent, each with the production condition that
  would surface it.
- Wrote 7 isolating tests and committed them **red** (`b7221f9`) before any fix. Inspecting
  that red run caught a real error: D2's test was failing on **D6's** mechanism, not its own.
- Defined the 7 invariants in `SYNC.md` §2 and stopped for review, as asked. Human chose
  the conflict policy (detect, flag, leave dirty) → D-10.
- Applied the fixes. 7/7 green. **Verified in both directions**: the original adapter against
  the *current* tests still fails 7/7, each on its own assertion.
- `SYNC.md` complete; `DECISIONS.md` D-10..D-12; `_work/COLLABORATION.md` created.

**Files touched**
- `new`  — `SYNC.md`, `tests/sync/*` (3 files), `_work/COLLABORATION.md`
- `edit` — `starter/sync/sync_adapter.py` (the file Task 5 is about), `DECISIONS.md`,
  `_work/TRAPS.md` (TR-12 → CONFIRMED), `_work/TODO.md`, `README.md`
- **`data/` untouched. `starter/sync/fake_erp.py` untouched, as the brief requires.**

**Findings carried forward**
- Two fixes needed more than the obvious change. I-1: trimming the trailing timestamp group
  is correct but stalls forever when one timestamp holds more rows than `page_size` — the
  naive fix introduces a worse bug than it repairs. I-7 is **not** "convert everything to
  UTC"; the cursor must stay in the ERP's zone or pagination breaks silently.
- The fixes convert loud corruption into quiet non-convergence, so `SYNC.md` §6 changes the
  monitoring from error-rate to **age** (`dirty_record_age`, `open_conflict_age`, `cursor_lag`).
- `run_sync.py` still reports one failure after the fix, and that is correct: it asserts every
  record converges, which is only true of an adapter that silently picks a conflict winner.

**Open / next**
- P4a (Task 4 PERF), the other binary task. Then Group B, starting with the eval harness.

---

## Session 05 — Task 4, and a measurement harness

| | |
|---|---|
| **Start** | 2026-09-01 18:05 |
| **End**   | 2026-09-01 20:15 |
| **Duration** | ~2 h 10 m |
| **Agent** | Claude Code, Opus 5 (1M context) |
| **Repo state at start** | commit `237f93a`, clean |

**Asked for**
1. Do Task 4, using small slices to rank and a large slice only to confirm.
2. Flag anything unusual, expensive, long-running, or needing a different model, **in
   advance** — so usage stays inside a known budget.
3. Add a re-processing guard: do not re-measure what has already been measured, and
   estimate before running.
4. Explain **why** the query takes ~100 hours — data volume or algorithm — and say whether
   renting a larger CPU/GPU server would be the answer.

**Done**
- Built `perf.sqlite` (11 s, 120 MB). **Never ran the baseline**, as the brief instructs.
- First calibration attempt — the smallest slice that exists, 1 tenant x 1 day, 2 output
  groups — **blew a 90 s cap**. That failure set the whole approach: per-metric ablation on
  a tiny slice first, composed into a model, validated on held-out slices.
- **Axis settled empirically**: cost tracks output *groups*, not rows. `s/group` varies 1.5x
  across a 63x range in events; `us/event` varies 26x. Held-out prediction: groups 89-137 s,
  events 15-319 s, truth **120.6 s**.
- Baseline estimate **~359,500 s (99.9 h)**, of which `repeat_items_prev_day` is 98%.
- **Rewrite: 7.337 s median over 5 runs**, byte-identical on 13 columns, plus
  `p95_latency_ms` verified independently 40/40. No index, no schema change.
- Built `src/perf/cache.py` per request 3: estimates before running, **refuses** anything
  over a predicted ceiling, caches on SQL + database identity (24.3 s becomes 0.016 s).
- Answered request 4 explicitly: **it is the algorithm, not the data.** 1.12M rows is
  115 MB and one pass costs 0.1 s; the baseline performs ~2.5x10^12 row examinations by
  rescanning the same table ~2.2 million times. A 10x faster machine gives ~10 h — still
  useless. The rewrite gives 7.3 s on the same laptop. No hardware purchase competes with
  a 40,000x algorithmic win, and the budget says "on a laptop" precisely to close that door.
  GPUs are irrelevant: SQLite is single-threaded and scan-bound.

**Files touched**
- `new`  — `PERF.md`, `starter/my_report.sql`, `src/perf/{slices,measure,cache,report}.py`,
  `_work/measurements.json`
- `edit` — `DECISIONS.md` (D-13..D-16), `_work/TRAPS.md` (TR-11 CONFIRMED), `_work/TODO.md`
- **`data/` and `starter/report_query.sql` untouched.** `perf.sqlite` is gitignored.

**Findings carried forward**
- Ablation says one column is 98% of the cost, but deleting it still leaves 7,260 s — 726x
  over budget. **The ranking is real and the fix cannot be local to the top of it.** Ranking
  columns would have produced a fix that was 726x short.
- The shipped reference records `elapsed_s = 3050.0`; the estimate is 118x larger. The
  reference *rows* are correct and the rewrite is verified against them; only the recorded
  time is disputed (D-15).
- The ledger contains **impossible calendar dates** (`2026-04-31`), so the textbook `LAG`
  rewrite of `repeat_items_prev_day` is silently wrong (825 -> 159). `check` caught it (D-14).
- `cache_size=256MB` — the knob everyone reaches for — made the query **slower** in both
  combinations tried. Measured, not assumed.
- The estimator initially mispredicted the rewrite by 30,000x and now declines outside its
  calibrated shape. An estimator confidently wrong outside its domain is worse than none.

**Open / next**
- Group B: the eval harness (P2), then the matcher (P3), then the error analysis (P5).

---

## Session 06 — Evaluation harness, then paused

| | |
|---|---|
| **Start** | 2026-09-01 20:15 |
| **End**   | 2026-09-01 21:45 |
| **Duration** | ~1 h 30 m |
| **Agent** | Claude Code, Opus 5 (1M context) |
| **Repo state at start** | commit `e9d591e`, clean |

**Asked for**
1. Build the eval harness (P2).
2. Flag anything needing extra resources or pointing at an algorithmic problem, and ask
   before spending.
3. Pause and mark a resume point.

**Done**
- `src/contracts.py` — the matcher/harness contract, defined before either side existed.
  `OrderLine` has **no field a label could arrive in**, so leakage is structural rather
  than conventional.
- `src/eval/segments.py` — six noise classes as a priority-ordered partition computed
  from the raw line alone (D-17). Measured 11 candidate features before choosing.
- `src/eval/{metrics,harness}.py` — precision@auto, coverage, net value, recall@3,
  refusal precision, nearest-rank p95, per-tenant/channel/class breakdowns, the
  precision-coverage sweep, determinism check, cross-tenant leak counting.
- `src/matching/baselines.py` — `NullMatcher` (the zero point, -16,800 s) and
  `NaiveAliasMatcher` (the obvious design, measured) (D-18).
- 26 tests across `tests/eval/`; 33 in the repo, all green.
- Paused at a clean tree with the resume point written into `TODO.md` §0.

**Files touched**
- `new` — `src/contracts.py`, `src/eval/*`, `src/matching/*`, `tests/eval/*`, `pytest.ini`
- `edit` — `DECISIONS.md` (D-17, D-18), `README.md` (run instructions), `_work/TODO.md`,
  `_work/TESTING.md`
- **`data/` and `starter/` originals untouched.**

**Findings carried forward**
- The section 6.2 answer is now a measurement, not a claim: accuracy ranks `naive_alias`
  **above** `null` (35.2% vs 29.8%) while net value ranks it 2.8x worse
  (-46,580 vs -16,800 s).
- `naive_alias`'s operating curve **slopes the wrong way** — raising the confidence floor
  0.55 → 1.0 drops precision 35.9% → 22.6%. TR-02 as a shape rather than a table.
- The segmentation transfers to the holdout (shares within ~1.5 points on five of six
  classes), which is what makes the per-class breakdown worth reporting at all.
- **A real defect in my own harness:** the operating curve read `candidates[0]` and ignored
  `item_code`, making a matcher that answers without publishing candidates invisible to the
  sweep. Caught by a test written before any matcher existed to hide behind it.
- Two of my own tests were wrong and were fixed rather than the code they accused.

**Open / next**
- **P3, the matcher.** `harness.build()` already looks for `src.matching.pipeline:Pipeline`,
  so it is picked up automatically once written. Build lanes in trap order, measure after
  each, and close D-05's and D-06's open loops rather than dropping them.

---

## Session 07 — Task 2 finished, Tasks 3 and 6 delivered, submission closed out

| | |
|---|---|
| **Start** | 2026-09-01 21:45 |
| **End**   | 2026-09-02 02:30 |
| **Duration** | ~4 h 45 m |
| **Agent** | Claude Code, Opus 5 (1M context) |
| **Repo state at start** | commit `b03ed25`, paused at P3 |

**Asked for**
1. Resume P3 and build the matcher lane by lane, verifying after each change.
2. Do not rush; prioritise data correctness and sound judgement over finishing.
3. Explain the cold-start stage before moving on.
4. Write `EVAL.md`, then self-check the whole submission against the brief.
5. A chronological problem log, and personal handover notes.

**Done**
- **Task 2 complete.** P3-0 index, P3-1 identifier lanes, P3-2 lexical candidates,
  P3-3 arbitration, P3-4 abstain classes, P3-5 calibration, P3-7 cold start,
  P3-8 `predictions.csv`. Final: 28.3% coverage at **99.2% precision**, 1 FP, 0
  cross-tenant, p95 1.5 ms.
- **Task 3 complete** (`EVAL.md`) and **Task 6 complete** (`SCALE.md`, 791 words).
- **`README.md` rewritten** with the three things §11 asks for.
- **`_work/verify_docs.py` built** — the T-D tier `TESTING.md` had been claiming since
  session 2 without it existing. It found two problems on its first run.
- `_work/PROBLEM_LOG.md` (29 obstacles as a causal chain) and `NOTES.md` (gitignored).
- Verified in `python:3.11-slim`, `--network none`: identical numbers.

**Files touched**
- `new` — `EVAL.md`, `SCALE.md`, `src/matching/{index,pipeline,text,refusals,calibration}.py`,
  `src/predict.py`, `tests/matching/*`, `predictions.csv`, `_work/{PROBLEM_LOG,verify_docs}`,
  `_work/ERROR_ANALYSIS_DRAFT.md`, `NOTES.md`
- `edit` — `README.md`, `PERF.md` (headline corrected), `DECISIONS.md` (D-17..D-31 + opening)
- **`data/` untouched. `starter/` untouched except `sync/sync_adapter.py`.**

**Findings carried forward**
- **D-03 confirmed decisively**: alias precision 35.9% → 100%, exactly as predicted.
- **The gate that matters is separation, not score** (D-23). The floor moves precision ~2
  points across its whole range; the margin moves it 81% → 100%.
- **Two planned components measured and never built** — the size filter (91.8%, below
  break-even) and the synonym table (improves ranking, degrades separation, net −360 s).
- **The labels contradict themselves** on 31 of 102 exact unique matches (D-25). The ceiling
  is label noise: an oracle over the available signals reaches 34.0% coverage and we are at
  81.4% of the achievable value.
- **A third instance of one defect shape** — a lane saying "nobody" instead of "not me",
  found by a build-time guard three files away.
- **Corrected my own PERF.md headline** from 7.337 s to the measured range 7.3–9.1 s. The
  single figure was true and presented the best case.

**Open / next**
- Four items for the human, recorded in `NOTES.md` §1: own the `EVAL.md` §3 conclusions,
  rehearse the walkthrough, make one scoped code change unaided and time it, send the
  questions in `_work/QUESTIONS.md` §1.

---

<!-- Template for the next entry — copy, do not delete.

## Session NN — <short title>

| | |
|---|---|
| **Start** | YYYY-MM-DD HH:MM |
| **End**   | YYYY-MM-DD HH:MM |
| **Duration** | |
| **Agent** | |
| **Repo state at start** | commit `<sha>` |

**Asked for**

**Done**

**Files touched**

**Findings carried forward**

**Open / next**

-->
