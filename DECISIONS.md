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
