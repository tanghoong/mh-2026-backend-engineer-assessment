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
