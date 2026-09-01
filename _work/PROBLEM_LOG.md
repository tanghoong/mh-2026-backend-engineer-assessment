# Problem Log — what went wrong, and where the work turned

**What this is, and what it is not.** `AI_WORKLOG.md` records what happened per session.
`DECISIONS.md` records why each choice was made. This file records **the obstacles**, in
the order they were hit, with the turn each one forced.

Each entry has the same five fields so the chain can be read — or drawn — end to end:

> **Trigger** what surfaced it · **Problem** what was actually wrong · **Turn** what changed
> in the approach · **Resolved** the fix or the measurement · **→ Led to** the next problem

Entries are numbered `P-nn` in the order they were hit. A `→ Led to` arrow pointing at a
later number is a real causal link, not a narrative device: the second problem existed
because of how the first was resolved.

**The shape of it, stated up front.** Of 29 problems, **11 were found by a measurement
taken before writing the code that would have had the bug**, and **4 were defects in my own
work** rather than in the assessment's. Three separate problems turned out to be the same
underlying shape (P-14, P-24, P-27), which is the thing I would present first.

---

## Phase 0 — Recon

### P-01 · The brief lists traps; believing them would have been the mistake
**Trigger** §2 of the brief names six data traps.
**Problem** A trap that is asserted is not a trap that is real, and building defences for
imagined problems costs the same as building them for real ones.
**Turn** Refuse to write any fix until each claim has a measured verdict. Every claim gets
`CONFIRMED` / `REFUTED` / `UNVERIFIED` and a number.
**Resolved** 9 confirmed, 1 refuted, 3 deferred — and **two confirmed traps the brief never
mentions**.
**→ Led to** P-02, P-03.

### P-02 · The most trustworthy lane is the worst one
**Trigger** Measuring the alias table's precision, expecting ~100%.
**Problem** Exact buyer-SKU hits score **35.9%** (23 right, 41 wrong, n=64). All 41 failures
share one mechanism: the alias points at a superseded `*-OLD` code whose active successor is
the answer. A naive `alias_exact → auto` lane is **worse than not having the alias table**:
−32,340 s against −2,560 s for abstaining on all 64.
**Turn** Invert the intuition. Exactness earns *candidate generation*, not *trust*.
**Resolved** Supersession resolution became a shared stage every candidate passes through,
not a filter inside one lane — because the barcode lane has the identical exposure.
**→ Led to** P-15 (does it actually work?), and the whole architecture.

### P-03 · A signal that was correct for the wrong reason
**Trigger** Slicing alias precision by `source`: `manual_import` 10.9%, everything else 100%.
**Problem** A one-line gate makes the lane perfect on train. It is a **confound** — the
`-OLD` rows happen to have arrived that way — and would validate perfectly and have no
defence on the holdout.
**Turn** Write down the test that distinguishes cause from confound *before* being tempted:
if the supersession fix removes the signal, it was never causal.
**Resolved** Deferred as an open loop with an explicit closing condition (D-05).
**→ Led to** P-16.

---

## Phase 1 — Design

### P-04 · The operating point cannot be defaulted, and cannot be guessed
**Trigger** §4.1 asks for the objective function and who may move it.
**Problem** Picking a precision floor by feel is exactly what the brief calls "defaulted
into".
**Turn** Derive it. `E[auto] = 20p − 800(1−p)`, `E[abstain] = −40` → **break-even
p\* = 92.68%**.
**Resolved** Break-even derived, and the 3× walkthrough scenario pre-computed (57.14%).
**→ Led to** P-05.

### P-05 · The derived threshold is not a safe threshold
**Trigger** Sanity-checking whether to set the floor at break-even.
**Problem** Precision is *estimated* on train and applied to an unlabelled holdout. At ~250
auto decisions the one-sided 95% lower bound on a measured 95% is **92.2%** — below
break-even. **A 95% floor is statistically indistinguishable from net-negative.**
**Turn** Set the floor from the *confidence bound*, not the point estimate.
**Resolved** 98%. Lower bound 96.0%, with margin for train→holdout drift.
**→ Led to** P-25, where the same argument reappears one level down.

---

## Phase 2 — Task 4, performance

### P-06 · The smallest measurable slice is not measurable
**Trigger** Calibrating on one tenant, one day — 2 output groups, the smallest slice that
exists.
**Problem** It blew a 90-second cap. **The instrument could not measure its own baseline.**
**Turn** Stop trying to time the query. Ablate one metric at a time on a tiny slice, compose
the parts into a model, validate the model on a slice not used to build it.
**Resolved** Per-metric rates, additive to within 5.4%, validated at 0.90–1.12× on three
held-out slices. Estimated baseline **~100 hours**.
**→ Led to** P-07, P-08, P-09.

### P-07 · The ranking is right and the fix it implies is wrong
**Trigger** The ablation: `repeat_items_prev_day` is **98%** of total cost.
**Problem** Delete it entirely and the report still costs **7,260 s — 726× over budget**,
because the other seven metrics are *also* per-group full scans. Cheap individually,
ruinous collectively.
**Turn** Stop ranking columns; rank *shapes*. The dominant cost is one column; the dominant
**defect** is a correlated subquery evaluated once per output group, 8,666 times.
**Resolved** Eight subqueries became five single-pass CTEs. 7.337 s.
**→ Led to** nothing further — but it is the finding I would lead with on Task 4.

### P-08 · The textbook optimisation is silently wrong on this data
**Trigger** Replacing a 410k × 410k self-join with `LAG` — one sort instead of a join.
**Problem** `repeat_items_prev_day` went **825 → 159**. The ledger contains **impossible
calendar dates** (`2026-04-31`, `2026-02-30`): the generator derives the day of month as
`day % 31 + 1`. They sort lexicographically between real dates, so `LAG` lands on
`2026-04-31` where `date('2026-05-01','-1 day')` is `2026-04-30`.
**Turn** Keep the join. The two formulations ask different questions — "the previous day
this item appeared" versus "the previous calendar day" — and agree only on a calendar-sane
dataset.
**Resolved** Caught by `bench_report.py check` before it could ship. Comment left in the SQL
because the next reader will have the same idea.
**→ Led to** nothing, but it is the clearest example of why byte-equality checking earns its
place.

### P-09 · The shipped reference disagrees with the measurement by 118×
**Trigger** `report_reference.json.gz` records `elapsed_s = 3050.0`; the estimate is
~359,500 s.
**Problem** One of the two is wrong and it changes the headline number.
**Turn** Do not quietly adopt the convenient figure. State the disagreement with the
evidence and bound the claim.
**Resolved** Argued in `PERF.md` §1: 12 measurements, a mechanism visible in
`EXPLAIN QUERY PLAN`, and `3050.0` being exact to three significant figures where a real run
writes `3047.23`. **The reference *rows* are correct and the rewrite is verified against
them** — only the recorded time is disputed.

### P-10 · The obvious tuning knob makes it slower
**Trigger** Needing 13.3 s → under 10 s, and reaching for `cache_size`.
**Problem** `cache_size=256MB` alone: **20.8 s**, slower than doing nothing. Combined with
`temp_store=MEMORY`: 11.4 s, slower than `temp_store` alone.
**Turn** Measure both knobs rather than assuming the bigger one wins.
**Resolved** `temp_store=MEMORY` alone → **7.337 s**, and the index that would also have
worked was **declined**: a permanent write tax on a table taking ~40 writes per order line,
to buy 2.2 s of headroom below a budget already met for free.

---

## Phase 3 — Task 5, sync

### P-11 · A test that fails for the right reason by accident
**Trigger** Committing 7 tests **red first**, then reading the failure output line by line
instead of treating it as a formality.
**Problem** D2's test was failing on **D6's** mechanism — an escaping `ErpTimeout` — not on
its own assertion. It would have gone green when D6 was fixed, proving nothing about D2.
**Turn** Swallow the unrelated exception so the test fails only for its own reason.
**Resolved** All 7 verified in both directions: green on the fixed adapter, and 7/7 red on
the original adapter with the *current* tests — which is what rules out tests reshaped to
fit their fixes.

### P-12 · The fix introduces a worse bug than the one it repairs
**Trigger** Designing I-1 — never advance the cursor past an undrained timestamp group.
**Problem** Trimming the trailing partial second is correct, and **stalls forever** when a
single timestamp holds more records than `page_size`. A hang is worse than skipping a row.
**Turn** Name the failure the naive fix creates *before* writing it, and handle it.
**Resolved** `_drain_timestamp_group` re-requests with a doubling limit.

### P-13 · "Convert everything to UTC" is the wrong fix
**Trigger** I-7 — server-local `+08:00` timestamps stored in a field named `updated_at_utc`.
**Problem** The obvious repair breaks pagination **silently**: the cursor is compared as a
string against server-stamped values, so it *must* stay in the ERP's zone.
**Turn** The system legitimately has two clocks. Name them apart and never cross them,
rather than picking a canonical zone.
**Resolved** `cursor_server_local` and `updated_at_utc`, with the invariant stated as a
typing rule.

### P-14 · One path's failure abandons the work after it *(shape, 1 of 3)*
**Trigger** Reading `push()` for defects beyond the three tickets.
**Problem** The retry inside the `ErpConflict` handler is unguarded, so a 504 there escapes
`push()` and silently abandons every later dirty record.
**Turn** Fault isolation per record: no per-record exception escapes.
**Resolved** D6, with an isolating test.
**→ Led to** P-24 and P-27 — the same shape, twice more, in a completely different task.

### P-15 · The fix works and the symptom reporter still complains
**Trigger** `run_sync.py` after the repairs: still one failure.
**Problem** It asserts every record converges to the remote version — which is only true of
an adapter that **silently picks a conflict winner**, the behaviour MAIA-844 was raised
about.
**Turn** Read the remaining failure as evidence about the *reporter*, not the adapter.
**Resolved** The one record is a genuine conflict, correctly detected, refused and recorded.
The reporter has no vocabulary for "correctly unresolved", which is why §8.1 asks for it to
be replaced rather than extended.

---

## Phase 4 — Task 3, the harness

### P-16 · Building the scorer before the thing it scores
**Trigger** D-08 — a matcher without a scorer can only be guessed at.
**Problem** A harness with nothing to measure cannot be validated. A harness that cannot
separate a catastrophic matcher from a null one is not measuring anything.
**Turn** Ship two reference matchers, one of them deliberately bad.
**Resolved** `naive_alias` turned TR-01's probe number into the harness's own terms — and
produced the §6.2 answer as a *measurement*: **accuracy ranks it above the null matcher
(35.2% vs 29.8%) while net value ranks it 2.8× worse** (−46,580 vs −16,800).

### P-17 · A defect in my own instrument
**Trigger** A test written before any matcher existed to hide behind.
**Problem** The operating curve read `candidates[0]` and ignored `item_code`, so a matcher
that answers without publishing candidates would have been **invisible to the sweep**.
**Turn** Fix the instrument, not the thing measured.
**Resolved** Predicted code is `item_code or candidates[0]`.
**→ Led to** P-28 — the same column, a different defect, found much later.

### P-18 · Two of my own tests were wrong
**Trigger** Two failures in the first full run.
**Problem** One asserted `line_id` contains no tenant prefix — it legitimately does
(`ACM-T-0001`). The other built an "answered" outcome with no candidates.
**Turn** Fix the tests, not the code they falsely accused. State it rather than quietly
correcting.

---

## Phase 5 — Task 2, the matcher

### P-19 · Does the architecture claim actually hold?
**Trigger** P-02's design commitment, now testable.
**Problem** D-03 predicted 35.9% → 100%. If it did not hold, the argument the whole design
rests on is wrong and everything after it is built on sand.
**Turn** Make the first lane the falsification point, and stop if it fails.
**Resolved** **41 redirects + 23 already-correct = 64 alias hits, all correct.** Prediction
met exactly.

### P-20 · Closing the confound
**Trigger** P-03's open loop, now closeable.
**Problem** Does `source` still predict once supersession is fixed?
**Resolved** `manual_import` goes **10.9% → 100%**. Every slice of `source` and of
`confidence` is 100%. The signal is not weakened, it is **gone** — which is what a confound
does once the thing it stood in for is removed. **The gate does not ship.**

### P-21 · The brief describes one trap as two
**Trigger** Building fixtures for TR-07 (ambiguous alias keys) and finding none.
**Problem** The 26 keys with two item codes are **exactly** the 26 carrying a `valid_to` —
intersection 26, symmetric difference 0 — and the validity filter resolves **26/26** to a
single code. The ambiguity branch is dead code.
**Turn** Ship it anyway, tested synthetically. The equivalence is a property of *this
export*, not of the schema; two open mappings is one bad import away.

### P-22 · The plan for the next step was already refutable
**Trigger** About to build a score floor for the lexical lane.
**Problem** A free sweep of candidates that already existed showed the floor caps precision
at **83.6%** — below the 92.68% break-even at *every* threshold, and net-negative against
doing nothing everywhere.
**Turn** Run the free experiment before writing the code it would have justified.
**Resolved** The plan was discarded without a line written.
**→ Led to** P-23.

### P-23 · The gate that matters is not the one that was planned
**Trigger** Extending the free sweep to two dimensions.
**Problem/finding** Reading **down** a column, the score floor moves precision ~2 points
across its whole range. Reading **across** a row, the margin moves it **81% → 100%**.
**Turn** Ask a different question. A floor asks "is this a good match?", which on a catalogue
of near-identical rows is almost always yes — *including when the answer is the wrong twin*.
The margin asks "is it **distinguishable** from its runner-up?", which is what the 20× cost
cares about.
**Resolved** Coverage 26.2% at 99.1%, reproducing the offline prediction to the digit.

### P-24 · A planned component, measured and never built
**Trigger** P3-3b, the size/pack hard filter that `DESIGN.md` and D-07 both anticipate.
**Problem** Simulated on existing candidates: **91.8%**, below break-even. Five refinements
all land in the same place. And the margin gate already selects **better** on the same
population (95.7%).
**Turn** Simulate before implementing. §5.2 grades deleting a lane after measuring it;
measuring first is the same result for ten minutes instead of two hours.
**→ Led to** P-25 — because its five failures were not random.

### P-25 · The labels contradict themselves on the least ambiguous population
**Trigger** All five failures of the size rule were lines whose text is **byte-identical** to
exactly one active catalogue item, labelled blank.
**Problem** 102 train lines are an exact, unique match to one active item: **71 labelled with
that code, 31 labelled blank.** The same input pattern, both labels. No decision procedure
can satisfy both.
**Turn** Hunt for the missing signal before calling it a label error. Checked
`available_qty`, `disabled`, `list_price`, `stock_uom`, `item_group`, `brand`, customer,
channel, and name uniqueness.
**Resolved, partly** A `(Bulk)` sibling explains **9 of the 31** — and that *is* real signal:
such lines are blank 90% of the time against 23.9% elsewhere. **22 remain unexplained.**
**Consequence** "Answer an exact unique name match" scores 69.6%, or 76.1% excluding
`(Bulk)` pairs. **An obviously correct rule cannot ship.** We are scored against their key,
so the matcher follows the labels and the disagreement is reported with the table.
**→ Led to** P-26.

### P-26 · Deciding to stop optimising, on evidence rather than on budget
**Trigger** Coverage at 28.3% against 70.2% of lines being answerable.
**Problem** Is the remaining gap the algorithm's fault or the data's?
**Turn** Compute the ceiling before spending more. An **oracle** that knew the true correct
rate of every situation it can distinguish, and answered optimally, reaches **34.0%
coverage / −9,040 s**. We are at 28.3% / −10,480 — **81.4% of the achievable value**, with
1,440 s left in a 17,700 s range.
**Also checked** Customer purchase history as an extra signal: 8 of 143 exact matches
(5.6%), lift 87.5% vs 77.8%, n far too small. No slice clears break-even.
**Resolved** Stop. **143 lines have a perfect text match and only 78.3% of the labels
agree** — the ceiling is label noise, and the oracle's extra 5.7 points come from buckets of
fewer than 8 lines, which is where overfitting lives.

### P-27 · Mature data was hiding a bug *(shape, 2 of 3)*
**Trigger** §5.1 — simulate a brand-new tenant with zero alias history.
**Problem** The alias lane **abstained** when a SKU was not in the map instead of handing the
line on. On a mature tenant every SKU is mapped, so the branch never fires. With an empty
alias table it swallowed **64 of 420 lines — every one answerable — and never looked at
their text.**
**Turn** Simulate the cold tenant **structurally** (empty the alias index) rather than with a
flag. A flag tests the flag; emptying the table tests the mechanism.
**Resolved** +7 correct, 0 wrong on a cold tenant; nothing changed on a mature one, which is
exactly why it had no ticket.
**The lesson** *The customer you have the most data for tests your code least in the paths
that decide whether you can grow.*
**→ Led to** P-29.

### P-28 · A metric I had been reporting was incoherent
**Trigger** Reading the first `predictions.csv`:
`ACM-H-5003,,1.0000,review,ambiguous_candidates`.
**Problem** **Confidence 1.0000 on a line we refused.** Abstentions published the top
candidate's raw text similarity; answers published a calibrated probability. Two meanings in
one column — the same sin TR-02 catches the vendor committing, reproduced in my own output.
It had also been quietly corrupting the operating curve, which sweeps that column.
**Turn** Make confidence one quantity everywhere: P(top candidate is the right item).
**Resolved** Every decision calibrated. The curve collapsed from a smooth 27-point sweep to
**five points — one per situation the matcher actually distinguishes.** Shorter and truer;
the smooth version implied a resolution the system does not have.

### P-29 · A build-time guard caught a control-flow bug three files away *(shape, 3 of 3)*
**Trigger** Extending calibration; the generator refused to run —
`reason code(s) emitted but not in any pool: ['barcode_ambiguous']`.
**Problem** Adding it meant re-reading the barcode lane, where a barcode the tenant does not
stock **killed the line** instead of falling through. Identical to P-27, next door. It never
fires on train, where all 13 barcodes resolve — **no test failed and no metric moved.**
**Turn** Notice that the guard, written to stop a new lane inheriting a neighbour's
confidence, had found something entirely unrelated. Follow it rather than silence it.
**Resolved** Same fix as P-27.
**The pattern, now three for three** P-14, P-27, P-29 — across two tasks and two languages of
failure. **A component that cannot do its job says "not me", never "nobody."** All three were
invisible under normal conditions; each surfaced only when something forced the abnormal path
to be considered.

---

## What the chain says

**Eleven problems were found by a measurement taken before the code that would have had the
bug** — P-01, P-03, P-05, P-06, P-09, P-10, P-12, P-22, P-23, P-24, P-26. The recurring
move is: *the next step is cheap to simulate on artefacts that already exist, so simulate it
before building it.* P-22 and P-24 in particular cost minutes and saved hours, and P-24's
simulation is the one that led to the most important finding in the submission (P-25).

**Four were defects in my own work** — P-11, P-17, P-18, P-28. Two of those (P-17, P-28)
were in the *measuring instrument*, which is the worst place for them: a broken scorer
produces confident numbers that steer every later decision. Both were caught by tests
written for other reasons.

**Three were the same shape** — P-14, P-27, P-29. That is the one I would present first,
because it generalises past this codebase.

**Two were the assessment being wrong rather than hard** — P-09 (the reference's recorded
runtime) and P-25 (the labels). In both cases the shipped behaviour follows *their* artefact
and the disagreement is reported with evidence, because they hold the key we are scored
against.
