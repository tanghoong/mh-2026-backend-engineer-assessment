# DECISIONS

One entry per choice that could reasonably have gone another way. Written as the decision is
made, not reconstructed afterwards. Evidence is rerunnable — probe scripts in `_work/probes/`,
trap evidence in `_work/TRAPS.md`.

Entries D-01 … D-09 predate any matcher code and come out of Task 1.

---

## D-01 — Objective function: precision floor **and** net-value maximisation, not either alone

**Context:** §1's cost table has to become something optimisable. Three shapes were available.
**Options:** (a) pure net-value maximisation under the 20× model; (b) fixed coverage target,
maximise precision; (c) net-value maximisation subject to a hard precision floor.
**Chose:** (c).
**Evidence:** (a) is the honest formulation but can select a high-coverage, lower-precision
point, and §5.4 states outright that 100 % @ 88 % loses to 70 % @ 98 % — so the grader's
utility is not purely the stated expectation. (b) decouples from the cost table entirely and,
worse, barely moves when the ratio changes from 20× to 3×, so it cannot answer the question
§12 will ask. (c) keeps the cost model doing the optimisation while giving the business one
legible knob.
**Reversal trigger:** if the floor turns out never to bind — the net-value optimum sits above
it at every operating point measured — the floor is decoration and (a) is the truthful
statement. Check once the precision–coverage curve exists (P2).

## D-02 — Precision floor at 98 %, not at the 92.68 % break-even

**Context:** the break-even precision derives exactly: `p* = 760/820 = 92.68 %`. Setting the
floor there maximises expected value if every input is exact.
**Options:** (a) floor at `p*` = 92.7 %; (b) 95 %; (c) 98 %; (d) 99 %.
**Chose:** (c).
**Evidence:** `p05_objective.py`. Precision is estimated on train and applied to an unlabelled
holdout, so the *lower confidence bound* is what must clear `p*`, not the point estimate. At
~250 auto decisions the one-sided 95 % lower bound on a measured 95 % is **92.2 %** — below
break-even, i.e. statistically indistinguishable from net-negative. The lowest floor that
clears is ≈95.5 %; 98 % gives a bound of 96.0 %, buying margin for train→holdout drift and for
the ratio being stated as "roughly" 20× (at 30×, `p*` rises to 95.1 %). (d) was rejected as
paying coverage for margin the confidence bound does not require.
**Reversal trigger:** more labelled volume. The floor exists to cover estimation error, so it
should fall toward `p*` as the interval tightens — not stay at 98 % out of habit. Revisit at
~1,000 labelled auto decisions.

## D-03 — Supersession resolution is a shared stage after every lane, not a fix inside the alias lane

**Context:** the alias lane resolves to superseded `*-OLD` codes (TR-01). The obvious fix is a
filter inside that lane.
**Options:** (a) filter disabled codes inside the alias lane; (b) drop disabled items from the
index entirely; (c) a shared answer-normalisation stage every candidate passes through;
(d) abstain whenever any lane hits a disabled code.
**Chose:** (c), with (d) as its behaviour when no active successor exists.
**Evidence:** alias-exact precision measures **35.9 %** (23 correct / 41 wrong, n=64,
`p04_alias_precision.py`); **41/41** failures are the same mechanism, and 38/38 `-OLD` items
have an active same-name successor. But the barcode lane has the identical exposure (22
colliding barcodes in acme, 16 in nordic, `p02`), so (a) would need re-implementing per lane
and again for every lane added later. (b) loses the ability to explain to a buyer why their
known SKU stopped working. (d) alone discards 41 recoverable lines, ~10 % of train.
**Reversal trigger:** if the business confirms a superseded item is sometimes discontinued
rather than replaced, the redirect becomes unsafe and this collapses to (d). Question filed at
`_work/QUESTIONS.md` §1b.

## D-04 — Ignore `customer_sku_map.confidence` entirely for gating

**Context:** the alias table ships a `confidence` column that reads like a calibrated prior.
**Options:** (a) use it as a floor; (b) use it as a feature in the arbitration score;
(c) ignore it for gating, retain it as displayed evidence.
**Chose:** (c).
**Evidence:** `p04_alias_precision.py` — precision at `confidence=1.0` is **22.6 %**, at 0.55
it is **100 %**. The column takes three discrete values and is independent of `source`. A
`>= 0.9` gate selects exactly the 41 poisoned rows and discards 11 correct ones. It is not
uninformative, it is anti-informative on this sample.
**Reversal trigger:** if the vendor documents how the column is produced and it turns out to
carry a real signal that this sample inverts by coincidence, re-measure. n=64 is small; the
effect is not.

## D-05 — Do **not** gate on `source != manual_import`, despite it scoring perfectly

**Context:** sliced by `source`, alias precision is 100 % for `confirmed_order` and
`inferred_match`, and 10.9 % for `manual_import`. A one-line gate makes the lane perfect.
**Options:** (a) ship the `source` gate; (b) fix the supersession mechanism (D-03); (c) both.
**Chose:** (b), and explicitly not (a).
**Evidence:** the correlation is a **confound**, not a cause — the `-OLD` rows happen to have
been imported that way. Applying D-03 first removes the signal completely (all 64 lines
resolve correctly regardless of `source`), which is the test that distinguishes the two. A
gate that is correct for the wrong reason validates perfectly on train and has no defence on
the holdout, where the confound need not hold.
**Reversal trigger:** if `source` retains predictive power *after* D-03 is applied, it is
carrying independent signal and becomes a legitimate feature. Re-measure after P3-1.

**RESOLVED at P3-1.** Re-measured with the supersession redirect in place. `manual_import`
goes from **10.9% to 100%**; every slice of `source` and every slice of `confidence` is now
100% (n=64). The signal is not weakened, it is **gone** - which is what a confound does once
the thing it stood in for is removed. The gate does not ship. Had it shipped, it would have
validated perfectly on train and had no defence on the holdout.

## D-06 — No semantic / embedding lane (provisional)

**Context:** §4.3 asks where an LLM or embeddings earn their place, and §5.2 grades deleting
them after measurement as a positive result.
**Options:** (a) build it, measure, keep or delete; (b) skip it and defend the skip;
(c) skip it silently.
**Chose:** (b) provisionally, revisited after P3-5.
**Evidence:** structural, not budgetary. **89 % of nordic's active catalogue** and 34 % of
acme's sit in twin groups whose members differ only by a pack token (`1L`/`2L`/`200ml`,
`p02`). Dense embeddings pull near-identical strings together — they optimise for exactly the
confusion that is expensive here. The expected effect is more recall where matching is already
easy and less separation where it is costly. Skipping it also keeps the system offline by
construction (§5.2 forbids inference-time network calls), removing the only component that
would have needed one.
**Reversal trigger:** the lexical lane plateaus with coverage clearly unclaimed *and* the
residual errors are semantic (a different word for the same thing) rather than dimensional
(the wrong size of the right thing). That is a question the P5 error analysis answers directly.

## D-07 — Pack size is a hard filter, not a score term

**Context:** twins differ only by size. The conventional treatment is to weight the size token
more heavily in the similarity score.
**Options:** (a) boost the size token's weight; (b) hard filter on a normalised size
signature; (c) a separate size-agreement model.
**Chose:** (b).
**Evidence:** a missing size token is not a low score, it is an unanswerable question. Under
(a) a line naming no size still produces a ranked list with a clear winner, and the system
answers confidently at 20× cost. Under (b) the same line yields candidates spanning more than
one size and abstains (`ambiguous_twins`) — which is the correct behaviour for `ACM-T-0006`
and its labelled-blank cohort (TR-03/TR-04). (c) adds a probabilistic component to a decision
that is deterministic once the units are normalised.
**Reversal trigger:** if abstention analysis shows the filter refusing lines where the size was
present but written in a form the normaliser missed, the defect is in normalisation, not in the
filter — fix there, do not soften the filter.

## D-08 — Build the evaluation harness before the matcher

**Context:** the natural order is matcher first, then measure it.
**Options:** (a) matcher first; (b) harness first; (c) in parallel.
**Chose:** (b).
**Evidence:** a matcher without a scorer can only be guessed at, not tuned, and §6 grades the
harness in its own right. It is also the precondition for D-06's reversal trigger and for D-05's
confound test — both are claims about measured deltas, and neither is provable without the
instrument existing first. Cost is ~1.5 h against a 4.5 h matcher budget.
**Reversal trigger:** none foreseen; if the harness were to exceed ~2 h it is being
over-specified and should be cut back to the metrics §5.4 actually scores.

## D-09 — Keep the tenant-isolation control although the trap it guards did not reproduce

**Context:** §2 states buyer SKUs can resemble another tenant's item codes. Exact-match checks
find **0/776** in the alias map and **0** across train and holdout order lines (`p02`).
**Options:** (a) drop the control as unnecessary; (b) keep it; (c) keep it and say nothing.
**Chose:** (b), with the refutation recorded (TR-09) and reported per §11.
**Evidence:** the two namespaces do not collide by construction — buyer SKUs are 9-digit
numerics, item codes are `ACM-`/`NRD-` prefixed. But §5.4 makes any cross-tenant resolution a
hard fail on the task, and the control (per-tenant indexes, tenant asserted at the boundary) is
free. Absence of evidence at n=776 is not evidence of absence, and the loss function is
one-sided.
**Reversal trigger:** none. A free control against a task-fatal outcome stays. What could
change is the *verdict*: fuzzy resemblance has not been tested, so TR-09 may yet be upgraded
before `EVAL.md`.

## D-10 — On a 409, refuse to resolve: detect, flag, leave dirty

**Context:** MAIA-844. The old handler refetched the remote *version* and rewrote our payload
with it, turning the ERP's "someone else changed this row" into permission to overwrite.
**Options:** (a) field-level merge; (b) newest `updated_at` wins; (c) detect, write nothing,
record the conflict, leave the record dirty for review.
**Chose:** (c).
**Evidence:** the same asymmetry as `DESIGN.md` §1, in a different system. Not pushing our edit
is **recoverable** — it is still local, still flagged, still visible. Overwriting theirs is
**unrecoverable** — gone from both systems, and nobody knows it existed. (a) needs a record of
which fields we changed, which `LocalRecord` does not have, and resolves a same-field collision
silently anyway. (b) depends on two clocks agreeing, which is exactly the trap I-7 documents,
and still discards one side without telling anyone.
**Cost accepted:** the local edit is delayed, indefinitely if nobody works the queue. `SYNC.md`
§6 names that as the second thing to break at 500 tenants and specifies the alert
(`open_conflict_age` p95 over one business day).
**Reversal trigger:** if the conflict rate makes the queue unworkable, move to (a) — but only
after adding change-tracking to `LocalRecord`, because merge without it is (b) wearing a
disguise.

## D-11 — At-least-once delivery, chosen over at-most-once

**Context:** I-4 moves the cursor advance to after the batch is applied, so a crash between the
two causes re-delivery.
**Options:** (a) cursor first (at-most-once, the existing behaviour); (b) cursor last
(at-least-once); (c) cursor and apply in one transaction.
**Chose:** (b).
**Evidence:** (a) is what D4 is — a mid-page kill loses every record between the cursor and the
last commit, permanently and silently. (b) re-delivers, which is harmless because `_apply` is
idempotent on `external_id`. (c) is the ideal and is not available: the cursor and the records
would have to share a transaction with a remote read, and the vendor gives no such handle.
**Consequence made explicit:** idempotent apply stops being a nice property and becomes a
*precondition*. A future change that breaks it reintroduces duplication with no test failing —
so it is asserted rather than assumed.
**Reversal trigger:** if re-delivery volume ever becomes a cost centre, the fix is a durable
per-record applied-version check, not a return to (a).

## D-12 — Commit the failing tests before the fixes, in a separate commit

**Context:** §8.1 asks for "a failing test that isolates it and passes after your fix", one per
defect, and warns that a single test going green because four things were fixed is worth much
less.
**Options:** (a) write tests and fixes together, then assert in prose that each test isolates
one defect; (b) commit the tests red first, fixes in a later commit.
**Chose:** (b) — `b7221f9` red, fixes after.
**Evidence:** under (a) the claim is unverifiable by a reader: a test written after its fix can
be shaped to pass. Under (b) checking out the earlier commit and running pytest shows all seven
failing, each on its own assertion. It also caught a real error: D2's test was initially failing
on **D6's** mechanism (an escaping `ErpTimeout`), not its own. That was only visible because the
red run was inspected line by line rather than treated as a formality.
**Reversal trigger:** none. This costs one extra commit.

## D-13 — Decline the index; buy the speed with a connection PRAGMA instead

**Context:** the rewrite landed at 13.3 s against a 10 s budget. Two levers were available.
**Options:** (a) an expression index on `match_event(tenant_id, substr(created_at,1,10),
item_code)`; (b) `PRAGMA temp_store=MEMORY`; (c) both.
**Chose:** (b).
**Evidence:** measured, not assumed. The index costs 1.6 s to build and 41 MB, and takes the
report to 7.0 s alone or 5.15 s with the PRAGMA. The PRAGMA alone reaches **7.337 s**, inside
budget. The ledger takes ~40 writes per order line at peak and the index sits on that hot
table, so it is a permanent write tax paid forever to buy 2.2 s of headroom below a budget
already met for free. Also measured and rejected: `cache_size=256MB` alone is **20.8 s**,
slower than doing nothing, and combined with `temp_store` it is 11.4 s, slower than
`temp_store` alone. The knob everyone reaches for made it worse in both combinations.
**Cost accepted:** `temp_store=MEMORY` moves sort scratch into RAM, so peak memory scales with
concurrency rather than with data. The mitigation is a concurrency limit on the report
endpoint, not a different PRAGMA.
**Reversal trigger:** volume growth or a tightened budget. The index is the first lever, and
`src/perf/cache.py` is the instrument that says when — it predicts cost from group counts
without running anything.

## D-14 — Keep the self-join in `td_repeat`; reject the window-function rewrite

**Context:** `repeat_items_prev_day` self-joins a 410k-row DISTINCT set. Replacing it with
`LAG(day) OVER (PARTITION BY tenant_id, item_code ORDER BY day)` is one sort instead of a
join — the textbook rewrite.
**Options:** (a) `LAG`; (b) the self-join.
**Chose:** (b).
**Evidence:** `LAG` is **wrong on this ledger** and `bench_report.py check` caught it —
`repeat_items_prev_day` for T001 on 2026-05-01 went 825 to 159. `make_perf_db.py` derives the
day of month as `day % 31 + 1` regardless of month length, so **impossible calendar dates**
(`2026-04-31`, `2026-02-30`, `2026-06-31`) exist as strings and sort lexicographically between
the real ones. `LAG` lands on `2026-04-31` while `date('2026-05-01','-1 day')` is
`2026-04-30`. The two formulations ask different questions — "the previous day this item
appeared" versus "the previous calendar day" — and they agree only on a calendar-sane dataset.
**Reversal trigger:** the ledger's dates being repaired at the write path. Until then the
comment in the SQL exists because the next reader will have the same idea.

## D-15 — State that the shipped reference's `elapsed_s` is wrong

**Context:** `report_reference.json.gz` records `elapsed_s: 3050.0`. My estimate for the same
query is ~359,500 s, 118x larger.
**Options:** (a) quote 3050 s and report a 416x speedup; (b) investigate and say so.
**Chose:** (b).
**Evidence:** the estimate is built from 12 measurements, additive to within 5-12% on three
held-out slices, and rests on a mechanism visible in `EXPLAIN QUERY PLAN` (`SCAN me8`
containing `SCAN me9`, no usable index). For 3050 s to be right this machine would have to be
~120x slower than the author's on a single-threaded SQLite scan. And `3050.0` is exact to
three significant figures with a trailing `.0`, where a real `bench_report.py baseline` run
writes a float like `3047.23`.
**Scope of the claim:** the reference *rows* are correct and the rewrite is verified against
them. Only the recorded elapsed time is disputed. Section 11 of the brief invites this.
**Reversal trigger:** the author showing a completed baseline run. The claim is about a
number, not about the data, and it is cheap to retract.

## D-16 — Build the estimator and measurement cache before doing the measuring

**Context:** the first calibration attempt — the smallest slice that exists, one tenant on one
day, 2 output groups — blew a 90 s cap. Measuring was going to be the expensive part.
**Options:** (a) measure carefully by hand and keep notes; (b) build an estimate-first,
cache-second harness and measure through it.
**Chose:** (b), at a cost of about 40 minutes.
**Evidence:** it paid for itself three times. It refuses runs whose predicted cost exceeds a
ceiling, which turns "do not run the full query" from advice into a guardrail. It returns
cached results for identical work against an identical database — 24.3 s becomes 0.016 s — and
keys the cache on the database's size and mtime, so rebuilding `perf.sqlite` invalidates the
cache rather than silently serving numbers from a different dataset. Building it also forced
the per-metric ablation into an executable form, which is what exposed the additivity check:
the isolated rates sum to within 5.4% of the measured whole.
**Amended during use:** the estimator initially predicted the CTE rewrite at 30,000x its
actual cost, because the model is calibrated for the baseline's correlated-subquery shape. It
now detects that shape and declines rather than answering. An estimator that is confidently
wrong outside its domain is worse than one that says nothing.
**Reversal trigger:** none. The cost was recovered inside the same task.

## D-17 — Noise classes as a priority-ordered partition, not overlapping flags

**Context:** section 6.1 requires per-noise-class breakdowns and notes the classes are not
labelled in the shipped data, so they must be defined and justified.
**Options:** (a) overlapping boolean tags (has_size, has_abbrev, is_short, ...); (b) a
priority-ordered partition where every line lands in exactly one class; (c) cluster the
raw text and name the clusters.
**Chose:** (b), ordered by *which lane will decide the line* rather than by which words it
contains.
**Evidence:** measured 11 candidate features first. Overlapping tags make per-class
precision unreadable — a line counted in three classes moves three numbers at once, so no
row of the breakdown can be acted on. The partition discriminates strongly and, more
importantly, **transfers**: train/holdout shares are 18.3/18.7, 1.4/1.3, 2.9/4.3, 7.6/9.3,
50.2/47.3, 19.5/19.0. No-answer rate by class on train: `identifier` **0%**,
`non_item_marker` **100%**, `underspecified` **100%**, `format_noise` 6%, `sized` 28%,
`plain` **56%**, against a 29.8% base. (c) was rejected as unexplainable in a walkthrough
and unstable across a re-run.
**Constraint that shaped it:** every class is computable from the raw line alone. A
segmentation that reads `gt_item_code` describes the answer key, not the input, and is
unavailable on the holdout — where the breakdown actually has to hold.
**Reversal trigger:** if error analysis (P5) shows failures concentrating inside one class
rather than across classes, the partition is too coarse there and that class splits.

## D-18 — Ship two reference matchers, including a deliberately bad one

**Context:** the harness was built before the matcher (D-08), so it had nothing to measure.
**Options:** (a) unit-test the metrics only; (b) also build reference matchers and score
them end to end.
**Chose:** (b) — `NullMatcher` and `NaiveAliasMatcher`.
**Evidence:** a harness that cannot separate a catastrophic matcher from a null one is not
measuring anything, and that claim needs a demonstration rather than an assertion. Scoring
the naive design turns TR-01's probe number into the harness's own terms: **35.9%
precision, net -46,580 s against the null matcher's -16,800 s — 2.8x worse than doing
nothing.** It also produced the section 6.2 answer as a measured fact: accuracy ranks
`naive_alias` **above** `null` (35.2% vs 29.8%) while net value ranks it far below. And its
operating-point curve slopes the **wrong way** — raising the confidence floor from 0.55 to
1.0 drops precision from 35.9% to 22.6% — which is TR-02 visible as a shape rather than a
table.
**Cost accepted:** two extra classes to maintain, and their reason codes stay in the
registered set.
**Reversal trigger:** none. `NullMatcher` is the permanent zero point; `NaiveAliasMatcher`
is the permanent "the obvious thing scores this badly" control.

## D-19 — TR-07 and TR-08 are one trap, not two; keep both defences anyway

**Context:** the brief §2 lists "the same buyer SKU pointing at two different codes" and
"expired mappings" as separate data defects. They are the same 26 rows.
**Evidence:** the 26 keys with more than one `item_code` are **exactly** the 26 keys
carrying a `valid_to` - intersection 26, symmetric difference 0. Filtering by validity at a
2026-07 order date resolves **26 of 26** to a single code, leaving zero ambiguous keys. The
shape is always the same: a buyer SKU was remapped and the old mapping was *closed* with
`valid_to` rather than deleted.

```
('acme','CUST-003','003793659')
   ACM-ANGL0502   valid 2026-01-01 .. (open)
   ACM-MASK0931   valid 2026-01-01 .. 2026-03-31
```

**Options:** (a) implement expiry only, and drop the ambiguity branch as dead code;
(b) implement both; (c) implement ambiguity only, treating expiry as a special case.
**Chose:** (b), with the ambiguity branch **tested synthetically** because no natural case
exists.
**Reasoning:** (a) is what the measurement invites and is wrong for one reason: the
equivalence is a property of *this export*, not of the schema. Two open mappings for one key
is one bad import away, and the failure mode if it happens is picking one arbitrarily at 20x
cost. A branch that is dead today and cheap to keep is not the same as a branch that is
unnecessary. (c) inverts the dependency and would silently use a 3-month-expired mapping.
**What this changes in the write-up:** the brief's two bullets get one answer, and the
distinction between "the ambiguity was resolved" and "the ambiguity never arose" is worth
stating - the second is true here and the first is what a reader would assume.
**Reversal trigger:** if a future export contains a key with two open mappings, the branch
stops being synthetic and TR-07 becomes independently confirmed.

## D-20 — Publish our own confidence, never the vendor's

**Context:** the alias rows carry a `confidence` the matcher could simply pass through.
**Options:** (a) pass `customer_sku_map.confidence` through as the published confidence;
(b) publish a per-lane value derived from measured precision.
**Chose:** (b). Provisional constants now, replaced by measured lane precision at P3-5.
**Evidence:** D-04 established the column is anti-informative (22.6% precision at 1.0, 100%
at 0.55). Passing it through would export that inversion to every downstream consumer, and
§5.3 requires `confidence` to be *comparable across lanes* - a vendor field describing one
lane's provenance cannot be.
**Guarded by a test:** `test_ta4_vendor_confidence_is_not_used_as_our_confidence` asserts no
published confidence is one of the three values that column takes. It is a cheap tripwire
against a future "just use the confidence we already have" refactor.
**Reversal trigger:** none for the pass-through. The provisional constants themselves are
temporary by construction and must be replaced at P3-5, not left to become permanent.

## D-21 — The lexical lane generates candidates before it is allowed to answer

**Context:** the obvious way to add lexical matching is to build it and let it answer,
then tune the threshold until precision looks acceptable.
**Options:** (a) build and enable in one step; (b) build it as candidate-generation only,
measure recall, and enable answering only once arbitration exists.
**Chose:** (b).
**Evidence:** the two questions are independent and answering them together makes both
unreadable. "Can the right item be found?" is recall; "should we commit?" is precision.
Staged this way, the measurement is unambiguous: **precision stayed at exactly 100.0% (76
TP, 0 FP) and coverage at 18.1%**, because nothing new was answered, while **recall@3 went
from 0% to 99.3%** on the lines the lane sees. Had they moved together, a precision drop
could not have been attributed to the score, the threshold, or a bug.
**What it bought immediately:** the diagnostic that shapes P3-3/P3-4. Of the 218 answerable
lines the lane sees, the correct answer is at rank 1 for 203 (93.1%), rank 2 for 12, rank 3
for 1, and missing for 2. Top-1 score separates answerable (0.904) from unanswerable
(0.549); the rank-1/rank-2 margin separates a correct top hit (0.085) from a wrong one
(0.025). **Two gates, both measured to work, before either was written.**
**Reversal trigger:** none - this is a build order, not a shipped behaviour. The lane stops
being candidate-only at P3-4.

## D-22 — Score against the whole catalogue rather than a candidate-generation shortcut

**Context:** the conventional shape is an inverted index to shortlist, then score the
shortlist.
**Options:** (a) inverted trigram index, score the shortlist; (b) score every active item
in the tenant.
**Chose:** (b).
**Evidence:** the catalogue is 502-1114 active rows per tenant, and measured **p95 latency
is 2.074 ms against a 250 ms budget** - two orders of magnitude of headroom. (a) would
introduce a second thing to tune, and a shortlist that drops the right item is a recall loss
that no amount of downstream scoring can recover. Exactness is affordable here, so it is
bought.
**Reversal trigger:** catalogue growth. `SCALE.md` puts this at 4M rows across 500 tenants,
where per-tenant catalogues are ~8k and this becomes ~10x today's cost - still inside
budget, but the shortlist earns its complexity somewhere past that. The trigger is measured
p95 crossing ~50 ms, not a feeling about size.

## D-23 — Arbitrate on separation, not on score

**Context:** the obvious gate for a lexical lane is a score floor.
**Options:** (a) score floor; (b) margin between the top two candidates; (c) both.
**Chose:** (c), but the weights are the opposite of what was expected.
**Evidence:** a 2-D sweep over candidates that already existed - free, no code written:

```
precision   floor=0.80   0.85   0.90   0.93   0.95
margin 0.00     81.1%   83.1%  83.1%  83.9%  83.5%
margin 0.10     98.3%   98.3%  99.1%  99.1%  99.0%
margin 0.15    100.0%  100.0% 100.0% 100.0% 100.0%
```

Reading **down** a column, the score floor moves precision about 2 points across its entire
range. Reading **across** a row, the margin moves it from 81% to 100%. The score floor is
nearly inert; the margin does the work.

**Why that is not a curiosity.** A score floor asks "is this a good match?". On a catalogue
of near-identical rows that question is almost always yes, including when the answer is the
wrong twin. The margin asks "is this match *distinguishable* from its runner-up?", which is
the question the 20x cost actually cares about. It generalises D-07 from pack sizes to every
attribute that separates two catalogue rows, without needing to enumerate them.

**Operating point:** floor 0.90, margin 0.10. Margin 0.15 reaches 100% precision but a lower
net value - it refuses lines worth more than the false positive it prevents.
**Measured:** coverage 26.2%, precision 99.1%, net -11,020 s, exactly reproducing the
offline prediction to the digit. Agreement between a model built from candidates and the
implementation is the check that the implementation has no bug.
**Reversal trigger:** if the catalogue becomes less homogeneous - fewer twin groups - the
margin loses its discriminating power and the floor matters more. Re-run the sweep per
tenant; nordic (89% twins) and acme (34%) may not want the same constants.

## D-24 — Do not build the size discriminator. Measured first, and it does not pay

**Context:** P3-3b was planned as a size/pack hard filter to recover coverage from lines the
margin gate refuses. `DESIGN.md` and D-07 both anticipate it.
**Options:** (a) build it and measure; (b) simulate it on existing candidates and only build
if it pays.
**Chose:** (b), and it does not pay, so it was never built.
**Evidence:** simulated over the 121 lines the margin gate refuses. The rule fires on 61 and
picks the labelled answer on 56 - **91.8% precision, below the 92.68% break-even**, worth
-440 s. Every refinement tried lands in the same place:

```
size picks exactly one                   n=61  91.8%   -440 s
size picks one AND it is rank 1          n=61  91.8%   -440 s
size set matches exactly, not subset     n=62  91.9%   -380 s
size picks one AND margin >= 0.04        n=61  91.8%   -440 s
size picks one AND margin >= 0.06        n=55  90.9%   -800 s
```

**And the margin gate already does better on the same population.** Of the 102 train lines
whose text is an exact unique match to one active item, the shipped matcher answers 23 and
gets 22 right (95.7%), abstaining on the rest. Adding the size rule would replace a 95.7%
selector with a 91.8% one.
**What this is worth saying:** §5.2 grades deleting a lane after measuring that it did not
pay as a positive result. Measuring *before* building is the same result for less time, and
the simulation cost about ten minutes against a couple of hours of implementation.
**Reversal trigger:** the label problem in D-25. If the 5 failures are mislabels rather than
signal, this rule is 100% and clearly pays. It is one answered question away from shipping,
which is why it is documented rather than forgotten.

## D-25 — The labels contradict themselves on the least ambiguous population

**Context:** the 5 lines the size rule gets "wrong" are each **byte-identical**, after
normalisation, to exactly one active catalogue item, and are labelled blank.

```
ACM-T-0015  '- Hitex Angle Grinder Disc 7" Flap'
ACM-ANGL0280   'Hitex Angle Grinder Disc 7" Flap'      <- unique active match, label blank
ACM-T-0001  'Tolsen Wall Plug 12mm Red'
ACM-WALL0029   'Tolsen Wall Plug 12mm Red'             <- unique active match, label ACM-WALL0029
```

**Evidence.** 102 train lines are an exact, unique match to one active item. **71 (69.6%)
are labelled with that code; 31 (30.4%) are labelled blank.** The same input pattern carries
both labels, so no decision procedure can satisfy both populations.

**Partly explained, and the explanation is a real signal.** A `(Bulk)` sibling accounts for
9 of the 31: where the matched item has a `XB` twin sharing its name and barcode, the line
is labelled blank **90% of the time** (9/10), against 23.9% (22/92) where it does not. That
is TR-14 confirmed by the labels: an exact match is not an answer when a pack variant makes
it ambiguous. The remaining 22 have no attribute that separates them - not
`available_qty` (49 labelled answers point at qty=0 items), not `disabled`, not price, not
`stock_uom`, not customer, not channel.

**What was checked before concluding.** `available_qty`, `disabled`, `list_price`,
`stock_uom`, `item_group`, `brand`, customer id, channel, and whether the catalogue name was
genuinely unique. None separates the two groups.

**Consequence for the design, and it is the reason this entry exists.** "Answer an exact
unique name match" scores **69.6%**, and 76.1% after excluding `(Bulk)` pairs. Both are far
below break-even, so the rule cannot ship - *even though it is obviously correct*. The
matcher abstains on most exact matches, which looks over-cautious until you see this table.
**We are scored against their key, so the shipped behaviour follows their labels and the
disagreement is reported rather than assumed away.**
**Reversal trigger:** confirmation that these are label errors. Then D-24 flips too, and
coverage rises materially. Filed as the first question in `_work/QUESTIONS.md` §1b.


## D-26 — Strip order language from the query; do not strip unknown tokens

**Context:** the largest refused population was 187 lines below the score floor, 102 of them
answerable and with the correct item **already at rank 1** - blocked at 0.72-0.89 rather than
mismatched. The blocker turned out not to be the product text.

**What is actually in those lines.** Tokens present in queries and absent from every
catalogue entry: `pls` (13), `send` (13), `urgent` (12), `need` (10), `item` (4); pack
quantities `x24` (8), `x12`, `x48`, `x6`, `case`, `dozen`, `pkt`; a little Malay (`mentega`,
`putih`, `paip`, `udang`); and genuine misspellings (`vermmont`, `20mmc`, `lass`, `ttape`).
Buyers wrap the item in a request and append how many they want. Neither narrows *which*
item it is, and both pad the query with trigrams no catalogue entry can match.

**Options:** (a) leave it; (b) an explicit stop-list of order language and pack quantities;
(c) drop every query token absent from the tenant vocabulary - self-calibrating, no list to
maintain; (d) both.
**Chose:** (b). Simulated on existing candidates before writing any of it:

| variant | coverage | precision | net |
|---|---|---|---|
| (a) baseline | 26.2% | 99.1% | -11,020 s |
| **(b) order-language stop-list** | **28.3%** | **99.2%** | **-10,480 s** |
| (c) drop tokens absent from vocab | 30.0% | 96.0% | -13,340 s |
| (d) both | 30.0% | 96.0% | -13,340 s |

**Why (c) loses despite more coverage.** It deletes the misspellings too - `vermmont`,
`ttape`, `lass` are absent from the vocabulary *by definition* - and those are exactly what
the character trigrams exist to absorb. It buys 1.7 points of coverage by destroying the
signal that makes the damaged lines matchable at all, and lands 3 points of precision worse
for a lower net value. The self-calibrating rule is the more elegant one, and it is wrong.

**Measured after building:** 28.3% / 99.2% / -10,480 s, reproducing the simulation exactly.

**Note on symmetry:** `normalise` builds the catalogue index as well as the query, so a
stop-word is removed from both sides. That is deliberate - the two have to be comparable -
and it is why `Nos` being both a stop-word and a `stock_uom` is harmless.

**Reversal trigger:** the stop-list is hand-written, so it is the part most likely to be
wrong for a tenant whose buyers write differently. It has one obvious home
(`text.STOP_WORDS`) precisely because a live change in the walkthrough is likely to land
there.

## D-27 — Four abstain classes, two of which claim to *know*

**Context:** the matcher had two refusal reasons, both of them "I could not decide". §5.3
names `not_an_item` explicitly and §5.1 requires an operator in the review queue to see
*why*. `"subtotal"` and "these two candidates are indistinguishable" were the same code.

**Options:** (a) leave one uncertain bucket and let the queue sort it out; (b) split by
score band; (c) split by *kind of unanswerability*, with detectors that run before scoring.
**Chose:** (c). Measured on train:

| reason | n | correct refusal | right answer in top 3 |
|---|---|---|---|
| `not_an_item` | 10 | **100%** | n/a |
| `out_of_domain` | 45 | **100%** | n/a |
| `ambiguous_candidates` | 139 | 27% | **99%** |
| `no_candidate_above_floor` | 106 | 29% | **99%** |

**The split is between certainty and uncertainty, not between scores.** The first two are
claims to knowledge and are held to 100% by a test; a detector that is merely usually right
belongs in the uncertain bucket with the others. The last two are uncertain *by
construction* - they exist because the system could not decide - so their low correct-refusal
rate is the expected shape, not a defect. Judging all four by one number would call the
system 44% right when two of its four behaviours are perfect and two are honest.

**The number that matters for the uncertain two is the last column.** When the system says
"you pick", the correct code is in the top 3 for **99%** of the lines that have one. §5.4
scores that, and it is what decides whether a 40 s abstention is cheap or merely correct.

**Two orderings that are load-bearing, and are asserted rather than assumed:**

* The detectors run **after** the identifier lanes. If the buyer gave us a SKU or a barcode
  they meant an item, and an explicit identifier outranks a heuristic read of their prose.
  Verified: 0 detector refusals on lines carrying an identifier.
* They run **before** scoring. Neither is a question about how close the match is -
  `"subtotal"` does not have a weak best candidate, it has no question. Scoring it first
  would produce a candidate list, and a candidate list invites a reviewer to pick from it.
  Certain refusals therefore carry **no** candidates, so the two refusal kinds look
  different to a human and not just to a grep.

**On the out-of-domain threshold.** 0.34 of the query's non-numeric tokens must appear
somewhere in the tenant's catalogue. It is chosen from a sensitivity sweep, not tuned: every
floor from 0.00 to 0.34 refuses only unanswerable lines, the first mistake appears at 0.40,
and by 0.60 it is discarding 23 answerable lines. **0.34 is the top of a plateau**, which is
the property that matters - a constant tuned to the last decimal would not survive the
holdout. A test pins the plateau, not the constant.

**Net value is unchanged** at -10,480 s: every line these detectors catch was already being
refused. They change what the refusal *says*, which is the deliverable §5.1 asks for and is
invisible to a metric that only counts answers.

**Reversal trigger:** a tenant whose catalogue vocabulary is small enough that ordinary
lines score below the domain floor - a brand-new tenant with 20 items, for instance. That is
the cold-start case (P3-7) and it needs the floor to scale with catalogue size, or to be
disabled until the vocabulary is established.
