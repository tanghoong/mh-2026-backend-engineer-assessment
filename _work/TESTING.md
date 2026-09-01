# Test Strategy — purpose, asset, acceptance

**Why this file exists.** The brief grades documents as much as code, so "is it done?" has
to be answerable for a `.md` the same way it is for a function. Every deliverable therefore
gets the same three columns:

> **PURPOSE** — what question does this artefact answer?
> **ASSET** — what form of evidence is acceptable (document / data / code)?
> **ACCEPTANCE** — the rerunnable check that says it is good enough.

A deliverable with no acceptance check is not finished, it is only written. Acceptance
checks are **rerunnable**, including the ones aimed at prose — that is what stops the
last-day rewrite from silently breaking an earlier claim.

---

## 1. Four tiers

| Tier | Guards against | Runs | Fails the build? |
|---|---|---|---|
| **T-C** Contract | The output is malformed or non-deterministic | `pytest tests/eval` · **implemented** | **Yes** |
| **T-A** Trap | A confirmed trap regresses | `pytest tests/sync` done · matcher traps pending P3 | **Yes** |
| **T-D** Document | A `.md` claims a number the code no longer produces | `python3 _work/verify_docs.py` | **Yes** |
| **T-W** Walkthrough | *I* cannot re-derive my own decision under questioning | human, out loud | n/a — but it is what is actually graded |

T-D is the unusual one and the most valuable here: the deliverables are full of numbers
(`35.9%`, `p95 = 180 ms`, `8,666 rows`), and every one of them is a hostage. T-D re-extracts
them from the live artefacts and diffs. It is cheap to build and it is the mechanism that
answers §6.5, "how do you avoid a benchmark that silently rots".

---

## 2. Tier T-C — contract tests

These encode §5.1 and §5.3 as executable rules. They are independent of match quality: a
matcher that abstains on everything must still pass all of them.

| ID | Purpose | Acceptance |
|---|---|---|
| T-C1 | Output schema is exactly as specified | `predictions.csv` header equals `line_id,item_code,confidence,decision,reason_code,candidates`; 300 rows; one per holdout `line_id`, no extras, no gaps |
| T-C2 | Determinism (§5.1) | Two runs from a cold process produce byte-identical files |
| T-C3 | **Tenant isolation (hard fail, §5.4)** | No `acme` row carries an `NRD-*` code and vice versa — checked on `item_code` **and** on every entry of `candidates` |
| T-C4 | Field domains | `decision` in {auto, review, reject}; `confidence` a float in [0,1]; `item_code` blank iff `decision != auto` |
| T-C5 | Explainability (§5.1) | Every row has a non-empty `reason_code` drawn from a closed, documented set — an unregistered code fails |
| T-C6 | Latency budget (§5.1) | Measured p95 ≤ 250 ms/line, cold caches excluded, reported as a number not an assumption |
| T-C7 | Offline (§5.2) | Test process runs with sockets stubbed to raise; any network attempt fails the suite |
| T-C8 | Candidate format | ≤3 `code:score` pairs, `|`-separated, scores non-increasing |

T-C3 deserves its own note: TR-09 **refuted** the cross-tenant trap as stated, and this test
exists anyway. The control costs nothing and the failure mode is task failure — that
asymmetry, not the evidence, is the reason to keep it.

---

## 3. Tier T-A — one test per confirmed trap

Each test is named for the single trap it isolates, and **must fail on the pre-fix code for
that reason alone**. The procedure is the same one the brief demands for Task 5 (§8.1), and
it is worth applying to Task 2 as well.

| ID | Trap | Fails before the fix because | Passes after because |
|---|---|---|---|
| T-A1 | TR-05 non-items | `"subtotal"` resolves to an `ACM-MISC*` code | Non-items are absent from the index; `not_an_item` emitted |
| T-A2 | TR-06 barcode collisions | A colliding barcode returns one arbitrary code | Ambiguous barcode yields `barcode_ambiguous`, not an answer |
| T-A3 | **TR-01 supersession** | `ACM-T-0010` returns `ACM-GIWI0811-OLD` | Returns `ACM-GIWI0811`; **and no output row anywhere is `disabled=1`** |
| T-A4 | TR-02 confidence decoy | A `confidence >= 0.9` gate admits the 41 poisoned rows | Alias gating ignores `confidence` entirely |
| T-A5 | TR-08 expiry | An alias row with `valid_to < order_date` is used | Expired rows filtered before the lane runs |
| T-A6 | TR-07 alias ambiguity | An ambiguous key answers with an arbitrary one of two codes | Handed to the lexical lane, or `ambiguous_alias` |
| T-A7 | TR-04 twins | `ACM-T-0006` (size absent) answers instead of abstaining | `ambiguous_twins` when candidates span >1 size |
| T-A8 | TR-04 size mismatch | A line naming `2L` matches the `1L` twin | `size_no_match` abstention |
| T-A9 | TR-03 abstain classes | All abstentions carry one generic reason | Four distinct reasons, each with non-zero support on train |

**Rule:** a test that goes green because several things were fixed gets split. If T-A3 and
T-A5 can both be made to pass by one change, one of them is not isolating what it claims.

### Task 5 mirrors this exactly

`tests/sync/` follows the same discipline, one file per defect, each named for its
mechanism, each asserting the **invariant restored** rather than the symptom observed. The
current `run_sync.py` is a symptom reporter — it says something is wrong, not what — and
§8.1 asks for it to be replaced, not extended.

---

## 4. Tier T-D — document tests

`_work/verify_docs.py`. Runs against the finished deliverables; no network, seconds.

| ID | Purpose | Acceptance |
|---|---|---|
| T-D1 | Length limits are real | `DESIGN.md` ≤ 1500 words; `SCALE.md` ≤ 800 words |
| T-D2 | Required sections exist | Each deliverable contains the headings its task section enumerates |
| T-D3 | `DECISIONS.md` well-formed | 8–15 entries; each has Context / Options / Chose / Evidence / **Reversal trigger** |
| T-D4 | **Numbers are live** | Metrics quoted in `EVAL.md` re-extracted from a fresh harness run and diffed; drift fails |
| T-D5 | `line_id`s are real | Every `line_id` named in `EVAL.md` exists in the train set (guards against a hallucinated example) |
| T-D6 | Traps are accounted for | Every CONFIRMED trap in `TRAPS.md` appears in a deliverable **or** on the explicit "not fixed, here is why" list |
| T-D7 | README commands run | Every fenced command in `README.md` is executed in a clean container and exits 0 (TR-13) |
| T-D8 | No stale `python3`/`py` mixing | No delivered file documents `py -3` |

T-D4 and T-D5 are the two that matter. §6.5 asks how a benchmark is stopped from silently
rotting; T-D4 *is* the answer, and it is more convincing demonstrated than described.

---

## 5. Tier T-W — walkthrough rehearsal

Not automatable, and the highest-weighted thing here. §12 gives 20 minutes of "we drive"
plus **20 minutes of live change**. The check is:

- For any three `DECISIONS.md` entries picked at random: re-derive the decision from the
  evidence **without reading the entry**. Failing this means the entry was written, not made.
- For the cost ratio changed from 20x to 3x: name which thresholds move, in which direction,
  and roughly how far — before opening an editor.
- For a new noise pattern handed over cold: name the file and function that changes, within
  30 seconds.

That last point is a **design constraint, not just rehearsal**. If a new noise pattern
cannot be absorbed in one obvious place, the architecture is wrong for the exam it will sit.
Normalisation, lane thresholds, and the abstain rules each need one obvious home.
Questions to rehearse against: `_work/QUESTIONS.md`.

---

## 6. What is deliberately not tested

Stated so it reads as a choice rather than an omission — and so it can be defended:

- **No property-based / fuzz testing.** The input distribution is the 720 shipped lines; a
  generator would test an imagined distribution instead of the real one.
- **No performance test on the matcher beyond p95.** §5.1 asks for one number, and there is
  no second budget to protect.
- **No coverage target.** Coverage would reward testing the easy paths; the trap tests are
  aimed at the expensive ones instead.
- **No integration test across tasks.** Tasks 2, 4 and 5 share no runtime. Wiring them
  together would be scope invented for its own sake.
