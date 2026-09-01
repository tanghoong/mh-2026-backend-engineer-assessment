# Error analysis — draft material for review

> **This is material, not the deliverable.** §6.3 says *"This section is where we learn the
> most about you; do not delegate it."* So what follows is the evidence assembled and my
> reading of it, clearly marked as mine. **The conclusions in `EVAL.md` need to be yours** —
> reviewed line by line, disagreed with where you disagree, and rewritten in your own
> reasoning. The walkthrough will drive from `EVAL.md`, and it will ask *why*, not *what*.
>
> Where I am uncertain, I have said so rather than smoothed it over. Those are the places
> worth arguing with first.

---

## 0. The whole failure surface, counted

Every way the matcher is not optimal on the 420 labelled lines:

| | n | cost class |
|---|---|---|
| correct answer | 118 | +20 s each |
| correct refusal | 124 | −40 s each, unavoidable |
| **A. false positive** | **1** | **−800 s — the only 20× error** |
| **B. refused, answer was rank 1** | **162** | −60 s each vs answering — *policy, not bug* |
| **C. refused, answer was rank 2–3** | **13** | −60 s each — **ranking failure** |
| **D. refused, answer not in candidates** | **2** | −60 s each — **recall failure** |

**The shape to notice first: the expensive population and the common population are
different, and §4 of the brief asks whether we noticed.** The common failure (B, 162 lines)
costs 60 s each and is a deliberate choice. The expensive failure (A) happens once. We have
traded a great deal of the cheap error to buy almost none of the expensive one.

---

## Group A — the only false positive

### 1. `ACM-T-0028` — and it is not a matching error

```
text      'Stallion Ball Valve 1-1/4" PVC'
answered  ACM-BALL0667  'stallion ball valve 1-1/4in pvc'
label     (blank — abstain)
reason    lexical_unique, confidence 0.9556
runners   ACM-BALL0662 0.880, ACM-BALL0037 0.852
```

**Root cause.** The query text is **byte-identical**, after normalisation, to exactly one
active catalogue item. The margin to the runner-up is 0.12. Every gate we have says answer.

**My reading, and it needs your judgement.** This is one of the 31 lines in D-25 — the
population where an exact, unique name match is labelled blank 30% of the time and labelled
with that code 70% of the time. **Our single 20×-cost error falls inside the one population
where the labels contradict themselves.**

**Be careful how strongly this is stated.** n = 1. "Our only FP is in the D-25 population"
is true and defensible. "All our errors are label errors" is not, and would read as excuse-
making. I would state the first and let the reader draw the second if they want to.

**Cost class** 20×, −800 s. **Fix** none available: no attribute separates the 31 blanks
from the 71 labelled ones (checked: `available_qty`, `disabled`, `list_price`, `stock_uom`,
`item_group`, `brand`, customer, channel, name uniqueness).

---

## Group C — 13 ranking failures, and they are mostly one missing capability

The answer was in the candidates but not at rank 1. **Two sub-groups, and they need
different things.**

### C1 · Trade abbreviations and Malay/English mixing — 8 lines, one missing capability

| # | line | text | picked | wanted |
|---|---|---|---|---|
| 2 | `ACM-T-0072` | `remax hex bolt m10x75 SS304` | `... hdg` | `... stainless 304` |
| 3 | `ACM-T-0153` | `Hitex Hex Bolt M10X75 SS316` | `... hdg` | `... stainless 316` |
| 4 | `ACM-T-0193` | `hitex hex bolt m10x50 SS316` | `... hdg` | `... stainless 316` |
| 5 | `ACM-T-0112` | `remax - hex - bolt - m8x75 - ZP` | `... hdg` | `... zinc plated` |
| 6 | `ACM-T-0071` | `tolsen GRINDING DISC 4.5" flap` | `... grinding` | `... flap` |
| 7 | `ACM-T-0166` | `BOSCO GRINDING DISC 5" FLAP` | `... grinding` | `... flap` |
| 8 | `ACM-T-0086` | `Vermont Safety topi keledar putih Ratchet` | `... red ...` | `... white ...` |
| 9 | `ACM-T-0249` | `Bosco Cable Tie 300mm putih` | `... black` | `... white` |

**Root cause, and it is a single one.** The buyer's vocabulary and the catalogue's
vocabulary differ on *attribute* words: `SS304`/`stainless 304`, `ZP`/`zinc plated`,
`GRINDING DISC`/`angle grinder disc`, `putih`/`white`, `topi keledar`/`safety helmet`.
Character trigrams absorb *typos* well — that is why they were chosen — but a synonym is not
a typo. `zp` and `zinc plated` share no characters at all.

This is precisely the brief's §2 warning: *"trade abbreviations (`S/S`, `ZP`, `SDS`),
Malay/English mixing (`skru`, `ayam`, `susu`)"*. **It is a missing capability, not a bug**,
and one table would address all eight.

**The fix I would make — and the measurement that says the obvious version of it is wrong.**

I built a synonym table from exactly these observed failures (`ss304`→`stainless 304`,
`zp`→`zinc plated`, `putih`→`white`, and so on) and simulated it:

| | coverage | precision | net |
|---|---|---|---|
| current | 28.3% | 99.2% | −10,480 s |
| with the synonym table | **26.9%** | 99.1% | **−10,840 s** |

**It fixes the ranking — all 8 become rank-1-correct — and loses money.** Only 4 of the 8
then clear the margin gate, and coverage falls elsewhere.

**Why, and this is the interesting part.** Expanding `SS316` → `stainless 316` makes the
query more similar to the right item **and to every other stainless item at the same time**.
The margin shrinks. Our gate is a *separation* gate (D-23), so a change that improves
ranking while degrading separation is net-negative by construction.

**What I would build instead, and I am genuinely unsure it pays.** Treat the attribute as a
*discriminator* rather than as text: if the query names a finish (`SS316`, `ZP`, `HDG`) and
exactly one candidate has that finish, take it — the same shape as the size rule. The size
rule measured 91.8% and did not pay (D-24), so this needs measuring before believing.
**This is the first thing I would do with another day.**

### C2 · Corrupted size and digit tokens — 5 lines, a data problem

| # | line | text | picked | wanted |
|---|---|---|---|---|
| 10 | `ACM-T-0030` | `Hitex PVCP ipe1 5mm Class E` | `25mm` | `15mm` |
| 11 | `ACM-T-0179` | `Remax Ball Valve " 1PVC` | `2in` | `1in` |
| 12 | `ACM-T-0233` | `1) Hitex Hx Bolt M6x0 Stainless 316` | `m6x50` | `m6x30` |
| 13 | `ACM-T-0206` | `Tolsen    Ange  Grinder  Disc  5''  Flap` | `7in` | `5in` |
| 14 | `NRD-T-0084` | `Sisu Pottao Fries Wedge 25.kg` | `1kg` | `2.5kg` |

**Root cause.** The size token itself is damaged — a digit dropped (`ipe1 5mm` for
`pipe 15mm`), a decimal point moved (`25.kg` for `2.5kg`), a space inserted mid-number. The
*product* is identified correctly; the *size* is not, and size is identity here (TR-04).

**Why this is the dangerous group even though it is small.** The wrong answer is a real,
active, plausible item of the same product in a different size. If the gates ever let one
through it ships the wrong goods and looks entirely reasonable on the picking list. **These
five are the population the margin gate exists for**, and it caught all five.

**Cost class** currently −60 s each (missed answer). Would be −800 s each if answered.
**Fix** I would not chase these. Recovering them means trusting a repaired size token, and a
size token we had to repair is exactly the one not to trust. **They should stay refused.**
The honest write-up is that this group is *correctly* refused, not that it is a failure to
fix — and I would say so rather than list them as things I ran out of time for.

---

## Group D — 2 recall failures

### 15. `ACM-T-0111` — compounded damage

```
text   'need Hitex PPVC Pipe 05mm Class E'
want   ACM-PVCP1009  'hitex pvc pipe 50mm class e'
got    ACM-PVCP0023 0.844, ACM-PVCP0941 0.844, ACM-PVCP0166 0.800
```
**Root cause.** Two corruptions at once — `PPVC` for `PVC` *and* `05mm` for `50mm`. Either
alone is survivable; together the right item does not reach the top 3. **Same family as C2**,
one degree worse. Same conclusion: correctly refused.

### 16. `ACM-T-0209` — a label problem, and the second of the six

```
text   'pls send Masking Tape 24mm High Temp'   uom_text 'pcs'
want   ACM-MASK0286B  'tolsen masking tape 24mm high temp (bulk)'
got    ACM-MASK0761 0.920, ACM-MASK0032 0.902, ACM-MASK0141 0.902
```
**Root cause.** The label is the `(Bulk)` variant. The line contains no `bulk`, `ctn`,
`carton`, `box` or `outer`; the customer has no bulk history; across all of acme exactly two
labelled lines point at a `(Bulk)` code and the other one (`ACM-T-0152`) literally says
`(Bulk)` in its text. **No input can produce that answer.**

**Cost class** −60 s. **Fix** none in code. This is TR-10/TR-14, and it is one of the ≥3
wrong-or-underspecified labels §6.4 asks for.

---

## Group B — 162 refusals with the answer at rank 1

**These are not failures and I would resist writing them up as failures.** They are the
operating point, and the operating point is a choice with a number attached.

Answering all 162 is measurable: of the population the margin gate refuses, the top candidate
is right **72%** of the time (`ambiguous_candidates`, 101/140) and **57%** (`below_floor`,
61/106). Both are far below the 92.68% break-even, so answering them loses money — a lot of
it, because each mistake costs 20× what the refusal did.

Four examples worth naming because they show *why* the gate refuses:

| # | line | text | what the gate saw |
|---|---|---|---|
| 17 | `ACM-T-0006` | `- Stallion Angle Grinder Disc Flap` | three candidates at 0.9492, differing only by size — **and the query names no size**. Label: abstain. The gate and the label agree. |
| 18 | `ACM-T-0007` | `Kanto Self Drilling Screw #8 x 3/4 Zinc Plated` | 0.9474 vs 0.9189, margin 0.029. Correct at rank 1, refused. **A genuine miss.** |
| 19 | `ACM-T-0018` | `Kanto Cable Tie 100mm Natural` | exact match at 1.000, runners-up at 0.920. Margin 0.08, just under the 0.10 gate. Correct, refused. **The clearest single argument for revisiting the constant.** |
| 20 | `ACM-T-0009` | `Remax/Ball/Valve/2"/SS304` | exact match at 1.000. Label: abstain. **A D-25 line** — refused for the wrong reason and right anyway. |

**#19 is the one I would put in front of them.** It is a perfect text match, correctly ranked,
refused by 0.02 of margin. It is also the argument *against* moving the constant: the same
0.02 is what refuses `ACM-T-0009`, which is labelled blank. **The gate cannot tell those two
apart, and neither can I.**

---

## What I would say the groups are

§6.3 asks specifically: which are one bug, which are one missing capability, which are data.

| Group | n | Kind | Verdict |
|---|---|---|---|
| C1 abbreviations / Malay | 8 | **One missing capability** | Real, addressable, and the obvious fix measured net-negative. Attribute-as-discriminator is the next thing to try. |
| C2 + D1 corrupted sizes | 6 | **Data problem** | Correctly refused. Recovering them means trusting a repaired size token, which is the one not to trust. |
| A + D2 + #20 | 3 | **Label problem** | D-25. No code fix. Reported with the table. |
| B | 162 | **Not a failure** | The operating point. Measurable, chosen, defensible. |

**Zero are "one bug".** That is worth saying explicitly, because it is the answer §6.3 wants
and because it would be suspicious if it were not checked: I looked for a single defect
behind several failures and did not find one. The bugs that did exist were found earlier and
by other means — the operating curve reading the wrong field, the alias and barcode dead
ends — and none of them is in this list because each was fixed before it could produce a
failure here.

---

## Where I am uncertain — argue with these first

1. **The margin constant (0.10).** `ACM-T-0018` is refused by 0.02 and is correct.
   `ACM-T-0009` is refused by the same 0.02 and is labelled blank. I cannot separate them,
   and I do not know whether 0.10 is right or merely the value that happened to fit.
2. **How hard to lean on D-25.** I believe the labels are inconsistent and I have the table.
   I do not know whether saying so reads as rigour or as excuse-making, and the difference
   is mostly tone.
3. **Whether C2 should be listed as failures at all.** I argue they are correctly refused.
   A reader could reasonably say I am relabelling a limitation as a policy.
4. **Only one false positive.** That is either a well-tuned system or a sample too small to
   have found the second one. At n=1 I cannot tell, and neither can the reader.
