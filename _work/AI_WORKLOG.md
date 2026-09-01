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
