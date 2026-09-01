# DESIGN — Task 1

> Written before any matcher code exists. Every number is reproducible from
> `_work/probes/` (`p05_objective.py` for §1, `p01`–`p04` for §4); trap evidence in
> `_work/TRAPS.md`. Model-assisted, per §11.

---

## 1. The objective function

**Maximise expected operator-seconds saved, subject to a precision floor on `auto`.**

Per line, from §1 of the brief: a correct auto saves 20 s, an abstention costs 40 s, a
wrong auto costs 20× an abstention (800 s). With `p` = P(this answer is correct):

```
E[auto]    =  20p − 800(1−p)  =  820p − 800
E[abstain] =  −40
```

Answering beats abstaining only when `820p − 800 > −40`, i.e.

> **p\* = 760/820 = 92.68 %**

That number does most of the design's work. One false positive erases **40 correct autos**,
or **20 abstentions**. The null matcher — abstain on all 300 holdout lines — scores
**−12,000 s**: the zero point a submission must beat, and it is not zero.

`p*` moves sharply with the ratio:

| cost ratio | 3× | 5× | 10× | **20×** | 30× | 50× |
|---|---|---|---|---|---|---|
| break-even precision | 57.1 % | 72.7 % | 85.7 % | **92.7 %** | 95.1 % | 97.0 % |

**The chosen operating point: a 98 % precision floor on `auto`, maximising net value
subject to it.** Not 92.7 %, for three reasons — all of which are about *estimation*, not
taste:

1. **Sample size.** Precision is estimated on train, applied to an unlabelled holdout. At
   ~250 auto decisions the one-sided 95 % lower bound on a measured 95 % is **92.2 %** —
   *below* break-even, i.e. indistinguishable from net-negative. The lowest floor that clears
   is ≈95.5 %; 98 % (bound 96.0 %) also buys margin for train→holdout drift.
2. **The ratio is "roughly" 20×**, and asymmetric: 30× moves `p*` to 95.1 %. A floor at
   break-even is correct only if the ratio is exactly right.
3. **Contamination is not in the 20×.** Wrong matches "quietly corrupt the alias table";
   TR-01 is that loop's observed end state. The stated cost is the *caught*-error cost.

**Who may move it**, deliberately separated: the **cost ratio** belongs to Ops/Finance, who
own the credit note and the churn — an input, not an engineering knob. **`p*` is derived**,
never chosen; change the ratio and it recomputes. The **margin** between `p*` and the floor
belongs to engineering and risk, and shrinks as labelled volume tightens the confidence
bound. **Coverage is an outcome, not a lever** — nobody raises it directly.

---

## 2. Pipeline

```
raw line ─► [0] normalise ─► [1] tenant index ─► [2] identifier lanes ─┐
             deterministic      deterministic       deterministic      │
                                                                       ▼
                                            [3] lexical candidates ─► [4] size
                                                  deterministic         arbitration
                                                    scoring             deterministic
                                                                       │
              ┌────────────────────────────────────────────────────────┘
              ▼
   [5] ANSWER NORMALISATION ─► [6] arbitrate & abstain ─► Decision
        deterministic              probabilistic
```

**Contracts.** Stages 2–4 emit `Candidate{item_code, lane, raw_score, evidence[]}`. Stage 5
rewrites or drops candidates and may not invent them. Stage 6 emits
`Decision{item_code|None, confidence, decision, reason_code, candidates[≤3]}`. A lane can be
deleted by removing its call.

**Stage 5 is where the design is opinionated.** The intuitive architecture places trust at
the point of generation: exact identifier hits are trusted, fuzzy text is not. On this data
that is inverted. Alias-exact hits — the highest-trust lane by name — measure **35.9 %
precision** (23 correct / 41 wrong, n=64), and all 41 failures resolve to a superseded
`*-OLD` code whose active successor is the label.

So **exactness earns candidate generation, not trust.** Supersession redirect, non-item
rejection and the tenant assertion are pulled out of the lanes into one deterministic stage
every candidate passes through; confidence is assigned afterwards, uniformly. A per-lane fix
would need re-implementing for the barcode lane (same exposure: 22 colliding barcodes in
acme, 16 in nordic) and for every future lane.

Deterministic stages run first: cheap, and their failures are *knowable* — a barcode either
resolves uniquely or it does not. The one probabilistic stage is last, converting evidence
into a decision against the §1 floor.

**Cold start.** A new tenant has no alias history: stage 2 is empty, stage 3 carries
everything. With no measured lane precision it inherits a pessimistic prior and a higher
floor, answering only on lexically unique, size-unambiguous matches. Behaviour differs
visibly — lower coverage, `cold_start_*` reason codes — and converges as confirmed orders
accumulate. The alias table is what matures; TR-01 shows it also decays.

---

## 3. Where an LLM or embeddings would earn their place

**Neither is used at inference.** Defending that, as §4.3 requires:

The cheaper mechanism tried first is character n-gram lexical matching plus an explicit
normalised **size/pack signature**. The reason to expect it to suffice is structural, not
budgetary: **89 % of nordic's active catalogue sits in a twin group** whose members differ
only by a pack token (`1L` / `2L` / `200ml`); acme is 34 %. Dense embeddings pull
near-identical strings *together* — optimised for exactly the confusion that is fatal here.
An embedding lane would raise recall where it is already easy and degrade separation where
it is expensive.

Where a model would genuinely pay is **offline, not in the request path**: auditing the alias
table. "These 41 rows point at superseded codes, here is the successor" is a judgement task
over a static table, run nightly with a human confirming — TR-01's fix generalised, out of
scope for 3 days.

The fallback question answers itself: §5.2 forbids inference-time network calls, so any model
must be local, which costs a pinned model, a build step and a re-index story (§9). Declining
it keeps the system offline by construction — there is no degraded mode to design, because
nothing can be unavailable. If the lexical lane plateaus with coverage clearly left on the
table and residual errors are semantic rather than dimensional, the decision reverses; that
trigger is recorded in `DECISIONS.md`.

---

## 4. The six most expensive ways this system can be confidently wrong

Ranked by measured exposure. All six are *false positives*: at 20×, no other class competes.

| # | Failure mode | Exposure (measured) | Mechanism that catches it |
|---|---|---|---|
| 1 | **Alias resolves to a superseded code.** The most-trusted lane returns a `*-OLD` item | 41 / 64 alias hits on train; alias precision **35.9 %** | Stage 5 supersession redirect; test asserts no output row is `disabled=1` |
| 2 | **A vendor `confidence` field is trusted.** `confidence=1.0` is **anti-correlated** with correctness | 22.6 % precision at 1.0 vs **100 %** at 0.55 | Column ignored for gating; confidence derived from our own measured lane precision |
| 3 | **Twin items separated only by pack size.** A missing size token is answered instead of refused | 392 acme / 468 nordic codes in twin groups | Size signature as a **hard filter**: candidates spanning >1 size → `ambiguous_twins` |
| 4 | **Junk lines matched to catalogue artefacts.** `"subtotal"` finds `DELIVERY FEE` | 29.8 % of train has no answer; 14 non-item rows, incl. an active `SAMPLE - DO NOT SELL` | Non-items excluded at index build; `not_an_item` detector before the score floor |
| 5 | **A colliding barcode treated as decisive.** The most convincing `reason_code` is not unique | 22 acme / 16 nordic collisions | Barcode answers only on a unique post-normalisation hit; else `barcode_ambiguous` |
| 6 | **A correct-for-the-wrong-reason gate.** `source != manual_import` scores 100 % on train — as a **confound** with `-OLD`, not a cause | 5 correct / 41 wrong sit in one `source` bucket | Fix the mechanism (#1), not the correlate; gate must survive removing the confound |

Failure 6 belongs here because it is the one that survives review and fails on the holdout:
the most expensive confident error available is one in *our own reasoning*, cheap to make
precisely because it validates perfectly.

The brief's claim that buyer SKUs resemble other tenants' codes did **not** reproduce (0/776
exact). Tenant isolation is still structural — per-tenant indexes, tenant asserted at the
boundary — because the control is free and §5.4 makes a breach a hard fail.

---

## 5. The boundary

**Out of scope for 3 days, deliberately:**

| Not building | What production evidence would change that |
|---|---|
| **A semantic lane** (§3) | Error analysis showing residual failures are *semantic* (another word for the same thing) rather than *dimensional* (the wrong size of the right thing) |
| **A real service.** One entry point with a typed contract satisfies "service-shaped"; HTTP and deployment are graded nowhere | A consumer that must call it over a wire |
| **Learning from operator confirmations** — Task 6's subject; TR-01 is what it looks like untended | The audit path first, plus a measured confirmation error rate: the loop inherits that rate at 20× cost, so it is a precondition, not a follow-up metric |
| **UOM quantity conversion.** `uom_reference.csv` disambiguates *identity* (pack size); converting quantities is order-capture, downstream | Matching correct, quantity the remaining error source |
| **Per-customer priors.** ~8 buyers per tenant here | Volume per buyer sufficient for the prior's own precision to have a tighter interval than the margin it buys (§1) |

**The assumption most likely to be wrong:** that supersession is always a redirect. The
labels say so — 38/38 `-OLD` items have an active same-name successor and every affected
label points at it. In production a superseded item is sometimes discontinued outright, and
redirecting then ships wrong goods confidently. Stage 5 therefore redirects only where an
active successor exists and abstains otherwise — the first question I would put to the
business (`_work/QUESTIONS.md` §1b).
