# Mindhive Backend Assessment 2026.1 — Submission

Standard library only. No network, no API keys, no Docker, no `pip install`. Python 3.10+.
**Everything below runs in about 45 seconds on a clean machine.**

**Verified in a clean offline container** — `python:3.11-slim`, `--network none`, nothing
installed — producing identical numbers. `pytest` is the *only* optional dependency and it is
needed for the test suite alone: nothing under `src/` imports it, so a grader without pytest
can still run the harness, regenerate `predictions.csv`, and check the documents.

The original brief is preserved verbatim at [`ASSESSMENT_BRIEF.md`](ASSESSMENT_BRIEF.md) —
moved, not edited, so it stays available now this file is the run guide.

---

## Running everything

```bash
# ---- Task 2 + 3: the matcher and its evaluation -------------------------- ~8 s
python3 -m pytest tests -q                                   # 94 tests
python3 -m src.eval.harness --matcher pipeline --curve --check-determinism
python3 -m src.eval.harness --compare                        # accuracy vs net value
python3 -m src.eval.harness --matcher pipeline --cold-start  # brief 5.1
python3 -m src.predict                                       # writes predictions.csv
python3 -m src.predict --check                               # validates it against 5.3

# ---- Task 5: the sync defects ------------------------------------------- ~1 s
python3 -m pytest tests/sync -q                              # 7 tests, one per defect
cd starter/sync && python3 run_sync.py                       # the symptom reporter

# ---- Task 4: performance ------------------------------------------------ ~35 s
cd starter && python3 make_perf_db.py --out ../data/perf.sqlite     # ~11 s, ~120 MB
python3 src/perf/cache.py --estimate starter/report_query.sql       # estimate, do NOT run
cd starter && PYTHONPATH=.. python3 bench_report.py check \
    --db ../data/perf.sqlite --module src.perf.report:run --repeat 5 --budget-s 10

# ---- the documents check themselves too --------------------------------- ~3 s
python3 _work/verify_docs.py
```

`data/perf.sqlite` is generated and gitignored — regenerate it, do not look for it.

## Results

| Task | | |
|---|---|---|
| **2 Matcher** | 28.3% coverage at **99.2% precision** on train, 1 FP, 0 cross-tenant, p95 **1.5 ms** | [`predictions.csv`](predictions.csv) |
| **3 Eval** | net **−10,480 s** against the null matcher's −16,800 | [`EVAL.md`](EVAL.md) |
| **4 Perf** | estimated baseline **~100 h** → **7.3–9.1 s**, byte-identical | [`PERF.md`](PERF.md) |
| **5 Sync** | 7 defects for 3 tickets, 7 isolating tests | [`SYNC.md`](SYNC.md) |
| **1 Design** | break-even precision **92.68%**, derived | [`DESIGN.md`](DESIGN.md) |
| **6 Scale** | first thing to break is **24.2 GB of resident index** | [`SCALE.md`](SCALE.md) |

## Where things are

| Path | |
|---|---|
| `src/matching/` | the matcher — index, lanes, arbitration, calibration |
| `src/eval/` | the harness, metrics, noise-class segmentation |
| `src/perf/` | Task 4 — slicing, the estimate-and-cache harness, the rewrite |
| `starter/` | shipped code, **unmodified**, except `sync/sync_adapter.py` which Task 5 repairs |
| `data/` | shipped data, **read-only** |
| `_work/` | the decision trail — trap register, problem log, questions, test strategy, AI log |

---

## What I skipped, and why

The brief says the timebox is mine to manage and that the argument gets graded. Six things
were deliberately not built, and **five of them were measured before being declined** rather
than dropped for time.

| Skipped | Why | Evidence |
|---|---|---|
| **Attribute discriminator** for trade abbreviations (`SS316`, `ZP`, `putih`) — the fix for the largest error group | The obvious version **measures net-negative**: a synonym table makes all 8 failures rank-1-correct and costs 28.3% → 26.9% coverage, −10,480 → −10,840 s. It improves ranking and degrades *separation*, and the gate is a separation gate. | `EVAL.md` §3 |
| **More coverage optimisation** | An oracle that knew the true correct-rate of every situation it can distinguish reaches 34.0%; we are at 28.3%, **81.4% of the achievable value**. The ceiling is label noise, not the algorithm. | `EVAL.md` §4 |
| **Size/pack hard filter** — planned in `DESIGN.md`, never built | Simulated on existing candidates: **91.8%**, below the 92.68% break-even. Five refinements land in the same place, and the margin gate already selects better (95.7%). | D-24 |
| **Semantic / embedding lane** | 89% of nordic's active catalogue sits in a twin group separated only by a pack token. Embeddings pull near-identical strings *together* — optimised for exactly the confusion that is fatal here. | D-06 |
| **A real HTTP service** | "Service-shaped" is satisfied by one documented entry point with a typed contract. Nothing in §5.4 scores a wire protocol. | `TODO.md` §1 |
| **Fitting the 22 unexplained labels** | Fitting them is fitting noise, and at 20× the wrong direction is expensive. | `EVAL.md` §4 |

**The one I would do first with another day** is the attribute discriminator — treating a
finish or a colour as a *discriminator* rather than as text, the same shape as the size rule.
That needs measuring before believing, because the size rule was measured and did not pay.

---

## Where I think the brief is wrong, ambiguous, or contradicted by the data

§11 invites this, so here it is with the evidence. Both are argued at length in the
deliverables; both are cases where the **shipped behaviour follows your artefact** and the
disagreement is reported rather than acted on unilaterally.

**1. The labels contradict each other on the least ambiguous population.** 102 train lines
are an exact, unique match to one active catalogue item after normalisation. **71 are
labelled with that code; 31 are labelled blank.** Nine of the 31 are explained by a `(Bulk)`
sibling — real signal, and a trap the brief does not mention. **Twenty-two are explained by
nothing measurable**: `available_qty`, `disabled`, `list_price`, `stock_uom`, `item_group`,
`brand`, customer and channel were all checked. The consequence is a design constraint, not
a complaint — "answer an exact unique name match" scores 69.6%, so an obviously correct rule
cannot ship. *(`EVAL.md` §4, D-25.)*

**2. `report_reference.json.gz` records `elapsed_s: 3050.0`; I estimate ~359,500 s — 118×
larger.** The estimate comes from 12 measurements, is additive to within 5–12% on three
held-out slices, and rests on a mechanism visible in `EXPLAIN QUERY PLAN`. `3050.0` is also
exact to three significant figures with a trailing `.0`, where a real `bench_report.py
baseline` run writes something like `3047.23`. **The reference *rows* are correct and the
rewrite is verified against them** — only the recorded time is disputed. *(`PERF.md` §1,
D-15.)*

**Two smaller ambiguities, resolved under stated assumptions:**

- §2 lists "the same buyer SKU pointing at two different codes" and "expired mappings" as
  separate defects. **They are the same 26 rows** — intersection 26, symmetric difference 0 —
  and the validity filter resolves 26 of 26. Both defences ship anyway, the second tested
  synthetically, because the equivalence is a property of this export and not of the schema.
  *(D-19.)*
- §2 warns that buyer SKUs may resemble another tenant's item codes. **On exact match this
  does not reproduce: 0 of 776.** The namespaces do not collide by construction. The tenant
  isolation control ships regardless — it is free, and §5.4 makes a breach fatal. *(TR-09,
  D-09.)*

---

## Tool attribution

Per §11. **This submission was built with Claude Opus 5, via Claude Code, throughout** — the
probe scripts, the prose in every deliverable, the test suites, and the sequencing proposals
are all substantially model-generated.

What is not: the method. Every trap was required to have a measured verdict before any fix
was written; every task was scoped against what the brief actually grades; and work was
halted twice to settle definitions before spending time on them.
[`_work/COLLABORATION.md`](_work/COLLABORATION.md) records who decided what and where each
side corrected the other, including four places the approach is exposed.
[`_work/PROBLEM_LOG.md`](_work/PROBLEM_LOG.md) records the 29 obstacles in the order they
were hit.

**Every number in every document is produced by a script in `_work/probes/`, by the test
suite, or by the harness, and re-runs in seconds.** `python3 _work/verify_docs.py`
re-derives the metrics quoted in `EVAL.md` from a live run and fails if they have drifted —
that check exists because the writing was delegated and the verification was not.

---

## Known limits

Stated because a submission that claims none is not credible.

- **Every threshold is chosen on 420 labelled lines.** The lexical lane measures 97.7%
  precision and its one-sided 95% lower bound is 90.2% — below break-even. At n=43 it
  **cannot be proved to pay**. It ships on the point estimate, with the interval reported.
- **Coverage is 28.3%**, which is low. §4 of `EVAL.md` argues the ceiling is in the labels,
  with the oracle bound. A reader is entitled to disagree with that argument.
- **The cold-start measurement uses acme and nordic's own order lines.** It shows the
  mechanism works; it does not predict what coverage a genuinely different tenant would see.
- **`DECISIONS.md` has 31 entries against the brief's suggested 8–15.** Each corresponds to
  a rerunnable measurement rather than an opinion, so deleting one deletes the measurement.
  The opening of that file names the three to read first.
