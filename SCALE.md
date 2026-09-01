# SCALE — Task 6

500 tenants, 4M catalogue rows, ~150k order lines a day, and an alias table that grows from
every confirmed order.

## 1. The first thing to break is memory, not compute

Measured on the shipped index: **5.9 KB per active item**, 1,616 items resident in 10 MB,
0.36 s to build.

| | today | at 500 × 8,000 items |
|---|---|---|
| resident, all tenants | 10 MB | **24.2 GB** |
| one tenant's index | — | 48 MB |
| build, one tenant | — | 1.8 s |
| p95 per line | 2.1 ms | **21.1 ms** |

**Compute is not the problem, and that is worth saying before optimising it.** Scoring is
O(catalogue) by choice (D-22), so p95 rises to 21 ms — 12× inside the 250 ms budget — and one
core sustains ~47 lines/s against a required 1.7/s.

**24.2 GB of resident index is the problem**, and the obvious fix costs something specific:
an LRU at 48 MB per tenant means an evicted tenant pays **1.8 s on its first line** — 7× over
a budget that is per-line, so one cold line breaks it. Mitigations: warm on the tenant's first
*event* rather than its first *line*, and shard by tenant so a box holds a stable working set.

**What breaks second is D-22's stated trigger.** Scoring every item is affordable at 8,000
and not at 200,000 — one large tenant pushes p95 past 500 ms. The reversal condition was
written down at the time: measured p95 crossing ~50 ms, not a feeling about size. Past it, an
inverted index shortlists first, costing a second thing to tune and a recall loss.

## 2. Re-indexing

No embeddings are used (D-06), so there is no model to re-run — but the question applies to
the trigram index. A tenant editing 40,000 items at 2am costs **~9 s** to rebuild, small
enough that incremental update is not worth its complexity.

A tenant mid-rebuild serves the **old** index, not a partial one: a partial index does not
fail, it silently answers from half a catalogue — a false-positive generator at 20× cost.

## 3. The alias feedback loop

**This does not need speculating about. The shipped data contains one that was left
untended**, and it is TR-01: of 64 buyer-SKU hits on train, **41 point at superseded `*-OLD`
codes**, giving that lane 35.9% precision — worse than not having the alias table at all.
That is what a confirmation loop looks like after a few years without a supersession policy.

Three mechanisms, in the order they earn their place:

1. **Never write a confirmation straight into the alias table.** A confirmation is evidence,
   not truth. Record it with its operator and the alternatives shown; promote it only after
   *k* confirmations from different operators. One mistake then costs one queue entry, not a
   permanent mapping.
2. **Age the table against the catalogue, not against the clock.** Every alias resolves
   through the supersession map on read (stage 5). TR-01 exists because the pointer was
   historical and nothing revalidated it; revalidating on read makes catalogue changes
   invalidate stale aliases automatically.
3. **Watch the loop, not the entries.** An entrenched wrong match shows up as *rising
   coverage with a falling override rate* — operators stop correcting because the answer is
   already there. `alias_exact` coverage climbing while its correction rate falls toward zero
   is the alarm, and it fires long before anyone notices the wrong goods.

At 20× cost the asymmetry decides the design: **an alias that should exist and does not costs
40 s; one that exists and is wrong costs 800 s and keeps costing it.**

## 4. Shipping a matcher change

**Shadow, then canary — and the honest problem is that ground truth arrives days late.**

Shadow first, comparing *decisions* rather than correctness: a change that alters 30% of
decisions is a different system whatever its precision turns out to be.

**The calibration table makes the wait shorter than it looks.** It maps each situation to
P(correct), so a shadow run yields the *distribution over situations* with **no labels at
all**. If the new build moves mass from `exact_identifier` into `ambiguous`, expected
precision falls and it is measurable on day zero. Ground truth is then needed to confirm a
*value*, not to detect a *change* — and detecting the change is what stops a bad deploy.

Canary second, on 5% of tenants, gated on the net-value number the harness prints. Roll back
on the FP count, not on coverage — coverage moves first and means nothing alone.

**What I would not do is A/B on accuracy.** §2 of `EVAL.md` shows accuracy ranking a
matcher that destroys 30,000 operator-seconds *above* one that does nothing. A test that
optimises the wrong metric ships the wrong system faster.
