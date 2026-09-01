# Trap Register — problem-first

**Rule of this file:** a trap is not real because the brief says so. Every entry moves
through the same gates, in order. Nothing gets a fix until its **Verdict** is `CONFIRMED`.

```
CLAIM  →  EVIDENCE  →  VERDICT  →  PROBLEM STATEMENT  →  SOLUTION (proposed)  →  TEST  →  FIX
 what        how it was          CONFIRMED /        what actually       what we would do    the failing      applied
 someone     measured, with      REFUTED /          goes wrong, in      about it, with      test that        + verified
 asserts     numbers             UNVERIFIED         one sentence        alternatives        isolates it
```

`Source` = who claimed it: `BRIEF` (assessment text), `OWN` (found by us in the data).
A `REFUTED` entry is **kept, not deleted** — knowing a stated trap is not real is itself a
finding, and §11 of the brief invites us to say the brief is wrong.

Evidence commands live in `_work/probes/`. Every number below is reproducible.

---

## Status board

| ID | Trap | Source | Verdict | Cost class | Solution status |
|----|------|--------|---------|-----------|-----------------|
| TR-01 | Alias table points at superseded `*-OLD` codes | **OWN** | CONFIRMED | FP (20x) | proposed |
| TR-02 | `confidence` column is a decoy, not calibrated | **OWN** | CONFIRMED | FP (20x) | proposed |
| TR-03 | ~1/3 of lines have no correct answer | BRIEF | CONFIRMED | FP (20x) | proposed |
| TR-04 | Active twins differing only by pack size | BRIEF | CONFIRMED | FP (20x) | proposed |
| TR-05 | Non-item rows sit inside the catalogue | BRIEF | CONFIRMED | FP (20x) | proposed |
| TR-06 | Barcode is **not** unique within a tenant | **OWN** | CONFIRMED | FP (20x) | proposed |
| TR-07 | Same buyer SKU maps to two different codes | BRIEF | CONFIRMED | FP | proposed |
| TR-08 | Expired mappings (`valid_to` in the past) | BRIEF | CONFIRMED | FP | proposed |
| TR-09 | Buyer SKUs that look like another tenant's codes | BRIEF | **REFUTED** (exact) | — | n/a, see note |
| TR-10 | Labels themselves are wrong | BRIEF | UNVERIFIED | scoring | not started |
| TR-11 | Task 4: wrong extrapolation axis | BRIEF | UNVERIFIED | wasted time | hypothesis only |
| TR-12 | Task 5: more defects than tickets | BRIEF | UNVERIFIED | marks | not started |
| TR-13 | `python3` not on PATH on this machine | **OWN** | CONFIRMED | delivery | proposed |

---

## TR-01 — The alias table points at superseded `*-OLD` codes

**Source:** OWN. The brief warns the alias map is "dirty" but does **not** name this mechanism.

**Claim.** A buyer-SKU exact hit in `customer_sku_map.csv` is the highest-confidence lane
available, so it should be answered automatically.

**Evidence.** Over `order_lines_train.csv`, joining on `(tenant, customer_id, buyer_sku)`:

| Slice | Correct | Wrong | Precision |
|---|---|---|---|
| **All alias-exact hits** | 23 | **41** | **35.9%** |
| `source=confirmed_order` | 14 | 0 | 100% |
| `source=inferred_match` | 4 | 0 | 100% |
| `source=manual_import` | 5 | **41** | **10.9%** |

64 of 420 train lines carry a `buyer_sku`; **all 64 hit the map**. Of the 41 failures,
**41/41 have the identical mechanism**: the alias resolves to `<CODE>-OLD` while the label
is the active `<CODE>`. Examples:

```
ACM-T-0010  sku 001245731  alias -> ACM-GIWI0811-OLD   gt = ACM-GIWI0811
ACM-T-0011  sku 001959523  alias -> ACM-ANGL0886-OLD   gt = ACM-ANGL0886
ACM-T-0024  sku 008981867  alias -> ACM-NITR0903-OLD   gt = ACM-NITR0903
```

Every `*-OLD` code in both catalogues has `disabled=1`, and **38/38 have an active
same-name successor** at the identical code minus the suffix (acme 23/23, nordic 15/15).

**Verdict.** **CONFIRMED.** This is the single most expensive trap in the assessment.
A naive `alias_exact -> auto` lane scores **35.9% precision** on the population it is
*most* confident about. At 20x FP cost that lane alone is deeply net-negative.

**Problem statement.** The alias table stores a *historical* pointer. It is never
invalidated when the catalogue supersedes an item, so alias age silently converts into
wrong-goods-shipped.

**Solution (proposed).** A **supersession-resolution step that runs on every lane's output,
not just the alias lane** — normalise any resolved code through an active-successor map
before it can be returned:

1. Build `superseded_map: {old_code -> active_code}` from the catalogue, keyed on
   `disabled=1` plus an active item with the same `item_name` (minus the `(superseded)` marker).
2. Any lane resolving to a disabled code is rewritten to its successor, and the
   `reason_code` records the rewrite (`alias_exact_superseded_redirect`).
3. If a disabled code has **no** active successor, abstain — never answer.

*Alternatives considered (to argue in DECISIONS.md):* (a) drop disabled items from the
index entirely — loses the ability to explain why a buyer's known SKU stopped working;
(b) abstain on any alias hitting a disabled code — safe, but throws away 41 recoverable
lines (~10% of train); (c) trust `source` instead — see TR-02, it is correlated but not causal.

**Expected effect.** Alias-lane precision **35.9% -> 100%** on train (64/64), coverage unchanged.

**Test to write.** `test_alias_superseded_redirect` — assert `ACM-T-0010` resolves to
`ACM-GIWI0811`, not `ACM-GIWI0811-OLD`; assert no prediction anywhere in the output set
has `disabled=1`. See `_work/TESTING.md` T-A3.

---

## TR-02 — The `confidence` column is a decoy

**Source:** OWN.

**Claim.** `customer_sku_map.confidence` is a usable calibrated prior; filter on it.

**Evidence.** Alias precision sliced by `confidence` alone, on train:

| `confidence` | Correct | Wrong | Precision |
|---|---|---|---|
| **1.0** | 12 | **41** | **22.6%** |
| 0.72 | 2 | 0 | 100% |
| 0.55 | 9 | 0 | 100% |

The distribution is only three discrete values (1.0 x427, 0.72 x173, 0.55 x176) and is
**independent of `source`** — every `source` appears at every `confidence`. The values
carry no information about correctness; here they are **anti-correlated** with it.

**Verdict.** **CONFIRMED.** `confidence` is worse than useless: using it as a floor
(`>= 0.9`) selects exactly the 41 poisoned rows and discards 11 correct ones.

**Problem statement.** A field that looks like a calibrated prior is an uncalibrated
free-text artefact of whoever wrote the row. Trusting a vendor-supplied confidence without
measuring it against labels is the failure.

**Solution (proposed).** Ignore `customer_sku_map.confidence` for gating entirely. Derive
our own per-lane confidence from measured precision on train, and say so explicitly. Keep
the column only as evidence in the `candidates` payload.

**Note.** `source=manual_import` *appears* diagnostic (10.9% vs 100%) but that is a
**confound** — the `-OLD` rows happen to have been imported that way. Fixing TR-01 removes
the signal entirely. Do **not** ship a `source != manual_import` rule; it would be a
correct-for-the-wrong-reason gate that breaks on the holdout. This distinction is worth a
DECISIONS.md entry on its own.

---

## TR-03 — ~1/3 of lines have no correct answer

**Source:** BRIEF §2. **Verdict:** **CONFIRMED.**

**Evidence.** `order_lines_train.csv`: **125 / 420 blank `gt_item_code` = 29.8%**.
Per tenant: acme 86/260 (33.1%), nordic 39/160 (24.4%). Holdout is 300 lines
(acme 190 / nordic 110) — assume a similar rate, so roughly 90 lines must be refused.

Inspecting the blank population shows **at least four distinct sub-populations**, which
matters because they need different detectors:

| Sub-population | Example | Detector |
|---|---|---|
| Not an item at all | `ACM-T-0027` "subtotal", `ACM-T-0014` "same as last month order" | stop-list + no-product-token |
| Wrong domain for the tenant | `ACM-T-0013` "Cadbury Dairy Milk 165g" in **acme** (hardware) | item_group / vocabulary coverage |
| Under-specified, ambiguous twins | `ACM-T-0006` "Stallion Angle Grinder Disc Flap" (no size) | two or more candidates tie, abstain |
| Brand or attribute not in catalogue | `ACM-T-0025` "Tolsen M8x75 Stainless" | brand absent from that group |

**Problem statement.** "Abstain" is not one class. Treating it as one produces a single
score floor, which is the wrong instrument for three of the four cases.

**Solution (proposed).** Four distinct `reason_code`s (`not_an_item`, `out_of_domain`,
`ambiguous_twins`, `no_candidate_above_floor`), each with its own detector, evaluated
before the score floor. Report abstention precision per reason in `EVAL.md`.

---

## TR-04 — Active twins that differ only by pack size

**Source:** BRIEF §2. **Verdict:** **CONFIRMED, and larger than the brief implies.**

**Evidence.** Grouping active items by `(brand, item_group, name-with-size-stripped)`:

| Tenant | Twin groups | Codes inside a twin group | Share of active catalogue |
|---|---|---|---|
| acme | 77 | 392 | ~34% |
| nordic | 174 | 468 | **~89%** |

Example — three active codes, identical but for the pack token:

```
NRD-FULL0120  Nordvik Full Cream Milk Fresh 1L     Carton = 10
NRD-FULL0348  Nordvik Full Cream Milk Fresh 200ml  Carton = 100
NRD-FULL0010  Nordvik Full Cream Milk Fresh 2L     Carton = 12
```

**Problem statement.** For nordic, **the size token is not a detail — it is the identity**.
Any similarity metric that treats `1L` / `2L` / `200ml` as low-weight tokens will confidently
return the wrong one. Lexical scoring on nordic without size-awareness is a false-positive
generator, and nordic is 37% of the holdout.

**Solution (proposed).** Extract a **normalised size/pack signature** (value + unit,
converted to a base unit) and use it as a *hard* filter, not a soft score term:

- size present in the line and matches exactly one candidate -> that candidate;
- size present and matches none -> abstain (`size_no_match`);
- size **absent** from the line but the candidate set spans more than one distinct size ->
  **abstain** (`ambiguous_twins`). This is the mechanism that catches `ACM-T-0006`.

*Alternative rejected in advance:* boosting the size token's TF-IDF weight — it degrades to
a score comparison, and the whole point is that a missing size is not a low score, it is an
unanswerable question.

---

## TR-05 — Non-item rows inside the catalogue

**Source:** BRIEF §2. **Verdict:** **CONFIRMED.**

**Evidence.** acme 8 rows, nordic 6 rows: `DELIVERY FEE` (x5 acme, x2 nordic),
`MISC CHARGE`, `OPENING BALANCE`, `SAMPLE - DO NOT SELL`. All carry `disabled=0`, all sit
on `ACM-MISC*` / `NRD-MISC*` codes. Note that `SAMPLE - DO NOT SELL` is an *active,
sellable-looking* row that must never be an answer.

**Problem statement.** These are ledger artefacts in an item table. They are short,
high-frequency English words, so they attract exactly the junk lines ("subtotal",
"delivery") that should abstain — a false-positive magnet. Their duplicated names also make
them permanently ambiguous among themselves (5 identical `DELIVERY FEE` codes in acme).

**Solution (proposed).** Exclude `*-MISC*` and the known non-item name set from the
candidate index at build time, and emit `not_an_item` when a line's best evidence points at
one. Record the exclusion list in `DESIGN.md` — it is a data assumption, not a rule.

---

## TR-06 — Barcodes are not unique within a tenant

**Source:** OWN. The brief mentions "embedded barcodes" but implies a barcode hit is decisive.

**Evidence.**

| Tenant | Items with a barcode | Distinct barcodes | **Collisions** |
|---|---|---|---|
| acme | 649 / 1148 | 627 | **22** |
| nordic | 281 / 524 | 265 | **16** |

Cross-tenant barcode overlap: **0**, so barcode is safe for tenant isolation.
Lines carrying `raw_barcode`: train 13, holdout 13.

**Verdict.** **CONFIRMED.** A `barcode_hit -> auto` lane is unsafe on ~38 items.

**Problem statement.** `barcode_hit` is the most intuitively trustworthy `reason_code` and
therefore the one most likely to ship ungated. It is decisive *only* when the lookup returns
exactly one active row.

**Solution (proposed).** The barcode lane returns a match **only if** the lookup yields
exactly one row after (a) tenant scoping, (b) disabled/supersession resolution (TR-01),
(c) non-item exclusion (TR-05). Otherwise it hands its candidates to the next lane and
records `barcode_ambiguous`. Low volume (13 lines, ~4.3% of holdout) — it must be cheap to
get right and must not be over-invested in.

---

## TR-07 — Same buyer SKU maps to two different codes

**Source:** BRIEF §2. **Verdict:** **CONFIRMED.**

**Evidence.** 26 `(tenant, customer_id, customer_sku)` keys resolve to more than one
`item_code`, e.g. `('acme','CUST-003','003793659') -> ['ACM-ANGL0502','ACM-MASK0931']` — an
angle grinder disc and a mask, i.e. genuinely unrelated. Also
`('acme','CUST-003','003349465') -> ['ACM-PVCP0896','ACM-PVCP1055B']`.

**Note:** in the train set, **0 of the 64 alias-hit lines land on an ambiguous key**. So this
trap is *latent on train* and may fire on the holdout. That is exactly why it must be handled
by construction rather than by observed error.

**Solution (proposed).** An ambiguous alias key does not answer from the alias lane; both
codes are passed as candidates to the lexical lane to disambiguate on the raw text. If the
text cannot separate them, `ambiguous_alias` abstention.

---

## TR-08 — Expired mappings

**Source:** BRIEF §2. **Verdict:** **CONFIRMED.** 26 rows carry a `valid_to` (mostly
`2026-03-31`); order dates in train/holdout are 2026-06/07, i.e. **after** expiry.

**Note:** as with TR-07, **0 train alias hits touch an expired row** — latent, may fire on
holdout. The 26 expired rows and the 26 ambiguous keys overlap (an expired row is often the
losing half of an ambiguous key), which suggests `valid_to` is the intended disambiguator.

**Solution (proposed).** Filter alias rows by `valid_from <= order_date < valid_to` before
use. Check first whether this alone resolves TR-07's ambiguity — if it does, TR-07 collapses
into TR-08 and they become one fix, which is worth stating explicitly.

---

## TR-09 — Buyer SKUs resembling another tenant's item codes

**Source:** BRIEF §2. **Verdict:** **REFUTED as an exact-match phenomenon.**

**Evidence.** Exact-string checks all return zero:

- alias `item_code` outside its own tenant's catalogue: **0 / 776**
- `customer_sku` equal to another tenant's `item_code`: **0 / 776**
- order-line `buyer_sku` equal to another tenant's `item_code`: **0** (train and holdout)
- order-line `raw_text` containing another tenant's `item_code` as a token: **0**

Buyer SKUs are uniformly 9-digit numerics (`001245731`); item codes are `ACM-`/`NRD-`
prefixed alphanumerics. The two namespaces do not collide by construction.

**Open.** Not yet tested: *fuzzy* resemblance, or a nordic-style product name appearing in an
acme line (`ACM-T-0013` "Cadbury Dairy Milk 165g" is the shape of this, and it is labelled
abstain — see TR-03). Re-run before writing `EVAL.md`; upgrade to CONFIRMED if found.

**Action regardless.** Tenant scoping is a hard fail (§5.4), so it is enforced structurally
— separate per-tenant indexes, tenant asserted at the API boundary — not by a filter that
could be bypassed. A test asserts no output row's code prefix disagrees with its tenant.
This exists **even though the trap did not verify**: cost of the control is ~0, cost of
being wrong is task failure.

---

## TR-10 — The provided labels are wrong

**Source:** BRIEF §6.4, which asserts they exist and asks for at least 3.
**Verdict:** UNVERIFIED.

Cheap checks already **rule out** the obvious structural forms — 0 labels point outside their
tenant's catalogue, 0 point at a `disabled=1` item, 0 point at a `*-OLD` code. So any label
errors are *semantic*, not structural, and will only surface from the Task 3 error analysis
by hand.

**Do not go looking for these now.** Defer to Phase 5; the error analysis is the instrument.

---

## TR-11 — Task 4: extrapolating along the wrong axis

**Source:** BRIEF §7.1 — "two of those give answers that differ by 4x, and only one is right."

**Verdict:** UNVERIFIED — hypothesis below, to be settled by ablation, not by argument.

**Facts established without running anything.** Reference result: **8,666 rows**, 40 tenants
x 4 channels x 61 days = 9,760 possible, so 88.8% dense. Recorded baseline
`elapsed_s = 3050.0` (**~51 min**), so the 10 s budget needs a **~305x speedup**.

**Hypothesis (to test, not to assert).** The 8 correlated subqueries re-execute **once per
output group**, and `match_event` carries only `idx_match_event_line`, so no subquery
predicate (`tenant_id`, `substr(created_at,1,10)`) is indexable — each becomes a full scan of
~1.12M rows. If so, **cost scales with output groups**, not rows-in-window, and narrowing the
window is a poor proxy for narrowing rows. Secondary hypothesis: `repeat_items_prev_day`
dominates because its inner `EXISTS` runs per candidate row, making it
O(rows_in_tenant_day x table) rather than O(table).

**Also observed (cheap, exploitable).** Five subqueries — `avg_accept_score`,
`max_latency_ms`, `avg_latency_ms`, `accepted_disabled` and `repeat_items_prev_day` — key on
**tenant-day only, not channel**, so their value is recomputed identically for all four
channels of a tenant-day. A tenant-day CTE computed once is a free ~4x on those terms with
byte-identical output.

**Ablation plan.** Measure a fixed slice, then remove one metric at a time and re-measure;
separately vary *days* at fixed tenants and *tenants* at fixed days to separate the axes.
Record the ranking including anything that surprises us — the brief grades the proof, not the
rewrite.

---

## TR-12 — Task 5: more defects than tickets

**Source:** BRIEF §8.2. **Verdict:** UNVERIFIED — reading done, mechanisms not yet proven by
test. Candidates noted from a first read of `starter/sync/sync_adapter.py`; each needs an
isolating failing test before it is written up, and one test per defect (the brief says a
single test that goes green because four things were fixed "is worth much less").

Cursor advanced before the page is applied; a cursor stored at second resolution against an
ERP that ties timestamps; `idempotency_key` mixing `time.time()` into the hash so a retry can
never match the 60 s exact-string window; the `ErpTimeout` retry path that cannot know the
write committed; the `ErpConflict` path re-writing with the remote's version and thereby
discarding the remote edit; local UTC compared against server `+08:00` strings. All are
**hypotheses at this stage** — listed so they are not lost, not as findings.

---

## TR-13 — `python3` is not on PATH on this machine

**Source:** OWN. **Verdict:** CONFIRMED. `python` and `python3` are both absent; only the
`py` launcher (Python **3.12.10**) resolves. Docker 29.2.1 is present but the assessment
needs none of it.

**Problem statement.** Local commands and delivered commands differ. The brief says "assume a
clean machine, `python3` only" and gives graders a 10-minute offline budget, so a README
written from local muscle memory would be undeliverable.

**Solution (proposed).** Author every documented command as `python3`; run locally via
`py -3`. Before submission, verify the README's exact commands in a clean container
(`docker run --rm -v .:/app -w /app python:3.11-slim`) — Docker used as a *verification* tool
only, never as the delivery mechanism.
