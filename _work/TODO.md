# Master Plan & Progress

**This is the handoff document.** If context is lost — new session, new model, another
person — read this file first, then `_work/TRAPS.md`, then `DECISIONS.md`. Everything
needed to resume is here or linked from here.

Budget: **14–18 h over 3 calendar days.** Spent so far: **~1.6 h**.
Timezone UTC+08:00. Update the status board on every session close.

---

## 0. Where we are right now

| | |
|---|---|
| **Current phase** | P1 complete → **P2 (eval harness) not started** |
| **Last commit** | see `git log` — P1 lands as `docs: Task 1 DESIGN.md + first 9 decisions` |
| **Blocking question for the human** | none open; OD-1/2/3 answered, see §5 |
| **Nothing is runnable yet** | No `src/`, no tests, no `predictions.csv` |

**One-line status:** traps confirmed with numbers, operating point derived (break-even
92.68 %, floor 98 %), `DESIGN.md` and `DECISIONS.md` D-01..D-09 written. Next executable
step is the eval harness (P2) — deliberately before the matcher, per D-08.

---

## 1. Scoping — what each task actually asks for

The failure mode of this assessment is building more than is graded. The brief grades
**reasoning artefacts** more heavily than code: 5 of the 6 tasks deliver a Markdown
document, and only Task 2 requires a data output. Read this table before starting any task.

| Task | Weight | **Primary asset** | Secondary | Explicitly NOT asked for |
|---|---|---|---|---|
| 1 Design | 20% | `DESIGN.md` (≤1500 w) | — | Any code. Written before code exists. |
| 2 Matcher | 25% | `predictions.csv` (300 rows) | source | A service, an API, a UI, a DB. "Service-shaped" ≠ a service. |
| 3 Eval | 20% | `EVAL.md` | harness code, 1 command | A dashboard. A plotting library. |
| 4 Perf | 15% | `PERF.md` | `my_report.sql` | Schema migration. A new DB engine. |
| 5 Sync | 15% | `SYNC.md` | fixed adapter + 1 test per defect | Touching `fake_erp.py` (**forbidden**) |
| 6 Scale | 5% | `SCALE.md` (≤800 w) | — | Any implementation. |
| — | — | `README.md`, `DECISIONS.md` | — | — |

**Consequences of that table, stated so they are not re-litigated later:**

- **Code exists to produce numbers that go into a document.** Any code that does not feed a
  claim in a `.md` is out of scope. No CLI polish, no logging framework, no config system.
- **Task 2's grade is precision, not architecture.** §5.4: 70% coverage at 98% precision
  beats 100% coverage at 88%. Effort goes into the abstain path, not into more lanes.
- **Task 4's grade is the diagnosis, not the rewrite.** §7: "A correct rewrite that lands
  inside the budget is table stakes." The ablation evidence is what is graded.
- **Task 5's grade is one isolating test per defect.** A big passing test suite scores less
  than four small tests that each fail for exactly one named reason.
- **`DECISIONS.md` is written continuously**, not at the end. Target 8–15 entries. It is
  read *before* the code (§0).

---

## 2. Ordering, and why this order

```
P0 Recon ──► P1 DESIGN ──► P2 Eval harness ──► P3 Matcher ──► P5 Error analysis ──► P7 Ship
   (done)                     (before the         (iterate         (by hand)
                               matcher!)          against P2)
                                   │
                                   ├──► P4a PERF   (independent, bankable)
                                   └──► P4b SYNC   (independent, bankable)
```

Three deliberate choices:

1. **The harness is built before the matcher.** A matcher without a scorer cannot be tuned,
   only guessed at, and §6 grades the harness in its own right. Building it first means every
   later change is measured, and it is the thing that makes "deleting the embedding lane was
   the right call" provable rather than asserted.
2. **Tasks 4 and 5 are banked in the middle, not left to the end.** They are independent of
   Tasks 2/3, they have crisp pass/fail criteria (budget met, tests green), and they are worth
   **30% combined**. Tasks 2/3 are open-ended and will absorb infinite time. Bank the certain
   points before spending on the uncertain ones.
3. **Error analysis comes after the matcher is frozen**, not during. §6.3 wants 20 named
   failures with root causes — that requires a stable system to have failed.

---

## 3. Phases

Legend: `[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocked

### P0 — Recon and scaffolding · **est 0.5 h · actual 0.6 h** · `[x]`

- [x] Read the brief; safety-audit the repo (no network, no shell-out, stdlib only)
- [x] Confirm toolchain: Python 3.12.10 via `py` only; Docker present but not needed
- [x] Preserve `README.md` → `ASSESSMENT_BRIEF.md`; commit clean baseline
- [x] Probe the data and confirm/refute the brief's stated traps → `_work/TRAPS.md`
- [x] Set up `_work/` (plan, traps, questions, testing, AI log, probes)
- **Output:** 9 traps CONFIRMED (2 found by us, not in the brief), 1 REFUTED, 3 deferred.

### P1 — Task 1: `DESIGN.md` · **est 2.5 h · actual 1.0 h** · `[x]`

- [x] **P1-a** Objective function — break-even `p* = 92.68 %` derived; floor set at 98 %
      because the 95 % lower bound at n≈250 on a 95 % floor is 92.2 %, *below* break-even
- [x] **P1-b** Pipeline decomposition, 7 stages, deterministic vs probabilistic marked
- [x] **P1-c** LLM/embeddings: declined at inference, argued structurally (twin groups)
- [x] **P1-d** Six failure modes, each with a measured exposure number
- [x] **P1-e** Scope boundary + the assumption most likely to be wrong
- [x] `DECISIONS.md` **D-01..D-09** written during the design

**Output:** `DESIGN.md` at 1,510 words. New probe `p05_objective.py` derives every §1 number.
**Carried forward:** D-01, D-02, D-05, D-06 each carry a reversal trigger that P2/P3/P5 must
actually check — they are open loops, not closed decisions.

### P2 — Task 3 part 1: the eval harness · **est 1.5 h** · `[ ]`

- [ ] `src/eval/harness.py` — one command over `order_lines_train.csv`
- [ ] Metrics: precision@auto, coverage, **net value under the 20x cost model**, recall@3,
      abstention precision per `reason_code`
- [ ] Segmentation: per tenant, per channel, and per **self-defined noise class**
      (§6.1 — classes are not labelled, we define and justify them)
- [ ] Precision-vs-coverage curve, not a single point (§6.2)
- [ ] p95 latency measurement built in from the start (§5.1 requires it *measured*)
- [ ] Baseline run against a null matcher (abstain on everything) to fix the zero point

**Done when:** `python3 -m src.eval.harness` prints the full metric block, and running it
twice gives identical output.

### P3 — Task 2: the matcher · **est 4.5 h** · `[ ]`

Build in trap order — the confirmed-expensive first. Measure after **each** lane and record
the delta in `DECISIONS.md`; a lane that does not pay gets deleted (§5.2 grades that
positively).

- [ ] **P3-0** Index build: tenant-scoped, non-items excluded (TR-05), supersession map
      built (TR-01), size signature extracted (TR-04)
- [ ] **P3-1** Exact/normalised identifier lane: barcode (TR-06 uniqueness gate) + alias
      (TR-07 ambiguity, TR-08 expiry, TR-01 redirect, TR-02 ignore `confidence`)
- [ ] **P3-2** Lexical candidate generation
- [ ] **P3-3** Size/pack arbitration as a hard filter (TR-04)
- [ ] **P3-4** Abstain detectors — four kinds, per TR-03
- [ ] **P3-5** Arbitration + calibration: one comparable confidence across lanes
- [ ] **P3-6** *Optional* semantic lane — only if P3-1..P3-5 leaves coverage on the table.
      Measure the marginal gain; **deleting it after measuring is an acceptable outcome**
- [ ] **P3-7** Cold-start behaviour for a tenant with zero alias history (§5.1) — must be
      *different*, and the difference must be stated
- [ ] **P3-8** Emit `predictions.csv` over the holdout, schema exactly per §5.3

**Done when:** all of — p95 ≤ 250 ms measured; zero cross-tenant violations; byte-identical
output across two runs; every row carries a `reason_code`.

### P4a — Task 4: `PERF.md` · **est 2.5 h** · `[ ]`

- [ ] Build `perf.sqlite` (~20 s, ~120 MB, gitignored)
- [ ] **Do not run the full query.** Measure slices; extrapolate; validate the axis (TR-11)
- [ ] Separate the axes: vary days at fixed tenants, then tenants at fixed days
- [ ] Ablate one metric at a time; rank by measured cost; report the surprises
- [ ] Rewrite → `bench_report.py check` byte-identical, median ≤ 10 s
- [ ] Add `p95_latency_ms` (nearest-rank, same tenant-day set) without blowing the budget
- [ ] Write up: what was left unfixed, trade-offs accepted, the honest ceiling at 50x

**Done when:** `check` prints `OK` + `PASS`, and the diagnosis ranking is backed by an
ablation table rather than by reasoning.

### P4b — Task 5: `SYNC.md` · **est 2.5 h** · `[ ]`

- [ ] Reproduce each ticket symptom deterministically (fixed seed) before diagnosing
- [ ] **One failing test per defect**, each named for its single reason (§8.1)
- [ ] Map defects to MAIA-812 / 830 / 844; find the latent ones (TR-12) and state the
      production condition that would surface each
- [ ] Fix, stating the **invariant restored** for each
- [ ] Crash-safety: the process can die at any moment (§8, end)
- [ ] The contract to ask the vendor for, in priority order + how to stay correct at "no"
- [ ] What breaks at 500 tenants x 5 min, and how we would know first

**Done when:** each test fails on the pre-fix adapter for its own reason and passes after,
demonstrated by running the suite against both.

### P5 — Task 3 part 2: error analysis by hand · **est 1.5 h** · `[ ]`

- [ ] 20 failures named by `line_id`: root cause, cost class, the fix
- [ ] Group them: one bug vs one missing capability vs unfixable data
- [ ] TR-10 — find ≥3 wrong or under-specified labels and argue them
- [ ] Regression safety: thresholds, gates, what breaks the build, anti-rot

**Explicitly not delegated to a model** (§6.3 says so, and the walkthrough will test it).

### P6 — Task 6: `SCALE.md` · **est 0.75 h** · `[ ]`

- [ ] First thing to break, with evidence from what was measured in P3/P4a
- [ ] Re-index cost if used; stale-index behaviour
- [ ] Alias feedback loop — note this is **TR-01 at scale**, the same mechanism
- [ ] Shipping safely: shadow/canary, and judging success when truth arrives days late

### P7 — Ship · **est 1.5 h** · `[ ]`

- [ ] Rewrite `README.md` as clean-machine run instructions (`python3`, offline, <10 min)
- [ ] `DECISIONS.md` final pass — 8–15 entries, each with a reversal trigger
- [ ] State what was skipped and why (§11 grades the argument)
- [ ] Tool attribution per §11
- [ ] **Verify in a clean container** (TR-13)
- [ ] Walkthrough prep from `_work/QUESTIONS.md`

**Total estimate: 17.25 h** — inside the 14–18 h band with roughly no slack. If time is
lost, P3-6 (semantic lane) and P6 are the designed sacrifices; P2 and P5 are not.

---

## 4. Time ledger

| Session | Date | Phase | Est | Actual | Note |
|---|---|---|---|---|---|
| 01 | 2026-09-01 | P0 | 0.5 h | 0.6 h | Recon, safety audit, trap verification |
| 02 | 2026-09-01 | P1 | 2.5 h | 1.0 h | DESIGN.md + DECISIONS.md D-01..D-09 |

---

## 5. Open decisions that need the human

Marked here rather than assumed. Each one changes downstream work.

| # | Decision | Why it cannot be defaulted |
|---|---|---|
| **OD-1** | ✅ **Answered:** precision floor + net-value maximisation. Floor 98 %. See D-01, D-02. |
| **OD-2** | ✅ **Answered:** skip the semantic lane, revisit after measuring. See D-06 — its reversal trigger must actually be checked at P5, not quietly dropped. |
| **OD-3** | ✅ **Answered:** `_work/` ships. `README.md` explains it; repo root stays limited to the brief's named deliverables. |

No open blocking questions. Next one likely to arise: whether `notes` is an input the
production matcher receives or a post-hoc annotation (leakage) — `_work/QUESTIONS.md` §1b.

---

## 6. Standing rules

1. `data/` and `starter/` originals are **read-only**. New files sit alongside; nothing is
   overwritten. `starter/sync/fake_erp.py` is forbidden to modify by the brief.
2. **No fix before its trap is `CONFIRMED`** in `TRAPS.md` with a number attached.
3. Every claim in a `.md` traces to a rerunnable probe or test. No asserted numbers.
4. Commit per phase step with a real message. One-commit repos are a negative signal (§3).
5. Locally run `py -3`; **write `python3` in anything delivered** (TR-13).
6. Close every session by updating §0, §4, and `_work/AI_WORKLOG.md`.
