# Mindhive Backend Assessment 2026.1 — Submission

> **STATUS: work in progress.** This file will become the "how to run everything on a
> clean machine with `python3` only" document required by the brief. It is a stub today.

The original assessment brief is preserved verbatim at
[`ASSESSMENT_BRIEF.md`](ASSESSMENT_BRIEF.md) — it was moved, not edited, so the task text
stays available for reference once this README is replaced with run instructions.

## Where things are

| Path | What |
|---|---|
| `ASSESSMENT_BRIEF.md` | The original brief, unmodified |
| `data/` | Shipped data. **Treated as read-only.** |
| `starter/` | Shipped starter code. **Originals treated as read-only**; new files sit alongside |
| `_work/` | Working notes: plan, trap register, invariants, open questions, test strategy, collaboration record, AI work log |
| `DESIGN.md` `DECISIONS.md` `EVAL.md` `PERF.md` `SYNC.md` `SCALE.md` | Deliverables (pending) |

## Tooling attribution

Per §11 of the brief: this submission was built with an AI coding agent in the loop.
[`_work/AI_WORKLOG.md`](_work/AI_WORKLOG.md) is a timestamped record of those sessions, and
[`_work/COLLABORATION.md`](_work/COLLABORATION.md) records who decided what and on what
grounds — including where each side's framing was corrected by the other.

Every number in every document is produced by a script in `_work/probes/` or by the test
suite, and re-runs in seconds. The writing was delegated; the verification was not.

## Running

Standard library only, offline, no API keys. Python 3.10+.

```bash
# Task 3 - evaluation harness over the labelled train set
python3 -m src.eval.harness --matcher null --check-determinism
python3 -m src.eval.harness --matcher naive_alias --curve
python3 -m src.eval.harness --compare          # accuracy against net value

# Task 5 - sync defect suite
python3 -m pytest tests -q
cd starter/sync && python3 run_sync.py

# Task 4 - performance (database build is ~11 s, ~120 MB, gitignored)
cd starter && python3 make_perf_db.py --out ../data/perf.sqlite
python3 src/perf/cache.py --estimate starter/report_query.sql    # estimate, do not run
cd starter && PYTHONPATH=.. python3 bench_report.py check \
    --db ../data/perf.sqlite --module src.perf.report:run --repeat 5 --budget-s 10
```
