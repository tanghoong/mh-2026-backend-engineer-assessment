# EVAL — Task 3

> Every number here is produced by `python3 -m src.eval.harness --matcher pipeline --curve`
> and re-derivable in seconds. Model-assisted throughout, per §11; §3's failures were read
> by hand, one line at a time.

**Headline, on `order_lines_train.csv` (420 labelled lines):**

| | |
|---|---|
| Coverage (`decision=auto`) | **28.3%** |
| **Precision on auto** | **99.2%** (118 TP, 1 FP) |
| Net value under the §1 cost model | **−10,480 s**, against the null matcher's −16,800 |
| recall@3 | 99.3% |
| Cross-tenant violations | **0** |
| p95 latency | **1.459 ms** (budget 250 ms) |
| Determinism | two runs, byte-identical |

**The claim I am making, and §5.4 asks for it explicitly: this is a 70-at-98 system, not a
100-at-88 one — and it is further along that axis than intended.** 28.3% coverage is low.
§4 below argues that the ceiling is in the labels rather than the algorithm, with the
measurement, and §5 says what would move it.

---

## 1. The harness

```bash
python3 -m src.eval.harness --matcher pipeline --curve --check-determinism
python3 -m src.eval.harness --compare            # accuracy against net value
python3 -m src.eval.harness --matcher pipeline --cold-start
```

One command, offline, stdlib. It was built **before the matcher** (D-08), which is not a
stylistic preference: a matcher without a scorer can only be guessed at, and the harness had
to be validated against something before it could be trusted to validate anything.

**It is validated by two reference matchers, one of them deliberately bad.** `null` abstains
on everything and fixes the zero point at **−16,800 s**. `naive_alias` is the design most
people write first — trust an exact buyer-SKU hit — and measures **35.9% precision**. A
harness that cannot separate those two is not measuring anything, and that has to be
demonstrated rather than asserted.

It also enforces, rather than reports: determinism (two runs diffed), tenant isolation
(counted on `item_code` **and** on every candidate, because a leaked candidate is a leak that
has not been returned yet), a closed `reason_code` set, and p95 latency by nearest rank.

### The noise classes

§6.1 notes the classes are not labelled, so they are defined here and justified. Two rules
shaped them:

1. **Computable from the raw line alone.** A segmentation that reads `gt_item_code` describes
   the answer key, not the input, and is unavailable on the holdout — where the breakdown
   actually has to hold.
2. **A partition, not overlapping tags.** Priority-ordered, so every line lands in exactly
   one class. Overlapping tags make per-class precision unreadable: a line counted in three
   classes moves three numbers at once, and no row of the table can be acted on.

The order is *which lane will decide the line*, not which words it contains — a line carrying
a buyer SKU is an `identifier` line even if it also has format damage, because the identifier
lane resolves it first and the damage never gets a vote.

| class | n | share | no-answer rate | coverage | precision | net |
|---|---|---|---|---|---|---|
| `identifier` | 77 | 18.3% | **0%** | 98.7% | 100.0% | **+1,480 s** |
| `non_item_marker` | 6 | 1.4% | **100%** | 0.0% | — | −240 s |
| `underspecified` | 12 | 2.9% | **100%** | 0.0% | — | −480 s |
| `format_noise` | 32 | 7.6% | 6% | 9.4% | 100.0% | −1,100 s |
| `sized` | 211 | 50.2% | 28% | 17.1% | 97.2% | −7,100 s |
| `plain` | 82 | 19.5% | **56%** | 4.9% | 100.0% | −3,040 s |

Base no-answer rate is 29.8%, so the classes discriminate strongly. **More importantly they
transfer**: train/holdout shares are 18.3/18.7, 1.4/1.3, 2.9/4.3, 7.6/9.3, 50.2/47.3,
19.5/19.0. A segmentation that only holds on the set it was designed on is a description of
that set.

`identifier` is the only class with **positive** net value. That is the whole design working:
the lane the brief's data most punishes for naivety (§2 below) is the one now carrying the
system.

---

## 2. Defending the metric

### What accuracy alone would have said

§6.2 asks the question directly, so here it is as a measurement rather than an argument:

```
matcher       accuracy  coverage  precision   net (s)   vs null
null            29.8%      0.0%         -    -16,800        +0
naive_alias     35.2%     15.2%     35.9%    -46,580   -29,780
```

**Accuracy ranks `naive_alias` above doing nothing. Net value ranks it 2.8× worse.**

Accuracy counts a correct refusal and a correct answer as the same event. The cost model
prices a wrong answer at 20× a refusal. On a set where **29.8% of lines have no correct
answer**, those two views do not merely differ in emphasis — they disagree about which
system to ship. Reporting accuracy here would have been reporting the wrong sign.

The same trap sits inside the shipped matcher's own table above: its accuracy is 57.6%,
which sounds mediocre and is meaningless. 99.2% precision at 28.3% coverage is the pair that
describes it.

### The operating-point curve

§6.2 asks for a curve, not a point. Since P3-8 the published `confidence` is a **calibrated
probability** — P(top candidate is the right item), measured per situation — so the sweep is
over one quantity rather than a mixture:

```
   floor  coverage  precision   auto    net (s)
  0.5741     86.9%     76.7%    365    -64,600
  0.7183     61.7%     84.6%    259    -34,060
  0.9556     28.3%     99.2%    119    -10,480   <- shipped, and the net-value optimum
  0.9872     18.1%    100.0%     76    -12,240
  0.9872      0.0%         -      0    -16,800
```

**Five points, because the matcher distinguishes five situations.** An earlier version of
this curve had 27 points and swept raw text-similarity scores; it was smoother and it implied
a resolution the system does not have. The short version is the true one.

Read across it: the shipped point is the net-value optimum. Being *more* conservative
(identifier lanes only) costs 1,760 s. Being more liberal costs an order of magnitude more,
because every step down the confidence ladder admits far more wrong answers than right ones —
which is what a 20× asymmetry looks like drawn out.

### The calibration behind it

| situation | correct/n | published confidence | 95% lower bound |
|---|---|---|---|
| exact identifier | 76/76 | 0.9872 | **96.6%** |
| lexical, separation-gated | 42/43 | 0.9556 | **90.2%** |
| ambiguous | 101/140 | 0.7183 | 65.5% |
| below floor | 61/106 | 0.5741 | 49.6% |
| certain refusal | 0/55 | 0.0 | — |

Confidence is Laplace-smoothed, `(correct+1)/(n+2)`, so it never publishes 1.000 — 76 for 76
is not proof that error is impossible.

**The second row straddles break-even and that has to be said out loud.** The lexical lane
measures 97.7%, and at n=43 its one-sided 95% lower bound is 90.2%, below the 92.68%
break-even. **We cannot yet *prove* it pays.** It ships because the point estimate says ship;
the uncertainty is reported rather than rounded away. This is `DESIGN.md` §1's argument one
level down, and it answers the question "which of your numbers would change most on a
different sample" — this one.

---

## 3. Error analysis

Read by hand, 20 failures, grouped by kind. The full working is in
`_work/ERROR_ANALYSIS_DRAFT.md`, including four places I am unsure.

**The whole failure surface first**, because the shape matters more than the list:

| | n | cost |
|---|---|---|
| correct answer | 118 | +20 s each |
| correct refusal | 124 | −40 s each |
| **A. false positive** | **1** | **−800 s** |
| **B. refused, answer at rank 1** | **162** | −60 s each — *policy* |
| **C. refused, answer at rank 2–3** | **13** | −60 s each — ranking |
| **D. refused, answer absent** | **2** | −60 s each — recall |

§4 of the brief asks whether the expensive mistakes and the common mistakes are different
populations. **They are, and by three orders of magnitude.** The common failure happens 162
times at 60 s; the expensive one happens once at 800 s. Almost all of the cheap error has
been traded to buy almost none of the expensive one.

### A. The only false positive — and it is not a matching error

**1. `ACM-T-0028`** `'Stallion Ball Valve 1-1/4" PVC'` → answered `ACM-BALL0667`, labelled
blank. The text is **byte-identical**, after normalisation, to exactly one active catalogue
item; margin to the runner-up is 0.12. Every gate says answer.

It is one of the 31 lines in §4 below. **Our single 20×-cost error falls inside the one
population where the labels contradict themselves.** Stated at that strength deliberately:
n=1, so "our only FP is in that population" is defensible and "all our errors are label
errors" is not.
*Cost 20×. Fix: none available — no attribute separates those 31 from the 71 labelled ones.*

### C1. Trade abbreviations and Malay/English mixing — 8 lines, **one missing capability**

**2–9.** `ACM-T-0072`, `ACM-T-0153`, `ACM-T-0193` (`SS304`/`SS316` → `stainless 304/316`,
each picking `hdg`), `ACM-T-0112` (`ZP` → `zinc plated`), `ACM-T-0071`, `ACM-T-0166`
(`GRINDING DISC` → `angle grinder disc`, each picking `grinding` over `flap`), `ACM-T-0086`
(`topi keledar putih` → `safety helmet white`, picking `red`), `ACM-T-0249` (`putih` →
`white`, picking `black`).

**Root cause, and it is a single one.** Buyer vocabulary and catalogue vocabulary differ on
*attribute* words. Character trigrams absorb typos — that is why they were chosen — but a
synonym is not a typo: `zp` and `zinc plated` share no characters at all. This is exactly the
brief's §2 warning about `S/S`, `ZP`, `SDS` and Malay mixing.

**The fix, and the measurement that says the obvious version of it is wrong.** A synonym
table built from precisely these failures:

| | coverage | precision | net |
|---|---|---|---|
| current | 28.3% | 99.2% | −10,480 s |
| with the synonym table | 26.9% | 99.1% | **−10,840 s** |

It makes **all 8 rank-1-correct and loses money.** Expanding `SS316` → `stainless 316` makes
the query more similar to the right item **and to every other stainless item at the same
time**, so the margin shrinks; only 4 of the 8 then clear the gate, and coverage falls
elsewhere. Our gate is a *separation* gate, so a change that improves ranking while degrading
separation is net-negative by construction.

**What I would build instead:** treat the attribute as a discriminator rather than as text —
if the query names a finish and exactly one candidate carries it, take that one. Same shape
as the size rule, which measured 91.8% and did not pay, so this needs measuring before
believing. **It is the first thing I would do with another day.**

### C2 + D1. Corrupted size tokens — 6 lines, **a data problem**

**10–15.** `ACM-T-0030` (`PVCP ipe1 5mm` → 15mm, picked 25mm), `ACM-T-0179`
(`" 1PVC` → 1in, picked 2in), `ACM-T-0233` (`M6x0` → M6x30, picked m6x50), `ACM-T-0206`
(`5''` → 5in, picked 7in), `NRD-T-0084` (`25.kg` → 2.5kg, picked 1kg), `ACM-T-0111`
(`PPVC ... 05mm` → 50mm, right item not in the top 3 at all).

The *product* is identified correctly; the *size* is damaged, and size is identity (TR-04).

**These six are the population the margin gate exists for, and it caught all six.** The wrong
answer in every case is a real, active, plausible item of the same product in a different
size — it would ship and look entirely reasonable on the picking list.

*Fix: none, deliberately.* Recovering them means trusting a repaired size token, and a size
token we had to repair is precisely the one not to trust. **They are correctly refused**, and
I would rather say that than list them as things I ran out of time for.

### D2 + label cases — 3 lines, **a label problem**

**16.** `ACM-T-0209` `'pls send Masking Tape 24mm High Temp'`, `uom_text='pcs'`, labelled
`ACM-MASK0286B` — the `(Bulk)` variant. No `bulk`/`ctn`/`carton`/`outer` token, no customer
bulk history, and across all of acme exactly two labelled lines point at a `(Bulk)` code —
the other one literally says `(Bulk)`. **No input can produce that answer.**
**17.** `ACM-T-0009` `'Remax/Ball/Valve/2"/SS304'` — exact unique match at 1.000, labelled
blank. **18.** `ACM-T-0015` `'- Hitex Angle Grinder Disc 7" Flap'` — same. See §4.

### B. The 162 — **not failures**

They are the operating point, and it has a number. Of the population the margin gate refuses,
the top candidate is right **72%** of the time (`ambiguous_candidates`) and **57%**
(`below_floor`) — both far below the 92.68% break-even, so answering them loses money, badly.

Four worth naming because they show *why*:

**19. `ACM-T-0006`** `'- Stallion Angle Grinder Disc Flap'` — three candidates at 0.9492
differing only by size, and **the query names no size**. Labelled abstain. Gate and label
agree; this is TR-04 working exactly as designed.
**20. `ACM-T-0018`** `'Kanto Cable Tie 100mm Natural'` — exact match at 1.000, runners-up at
0.920, margin 0.08 against a 0.10 gate. **Correct, and refused by 0.02.**

**#20 is the one I would put in front of a reviewer**, because it is also the argument
*against* moving the constant: the same 0.02 refuses `ACM-T-0009` (#17), which is labelled
blank. **The gate cannot tell those two apart, and neither can I.**

### The grouping §6.3 asks for

| group | n | kind |
|---|---|---|
| C1 | 8 | **one missing capability** — real, addressable, obvious fix measured net-negative |
| C2 + D1 | 6 | **data problem** — correctly refused |
| A + D2 + #17 | 3 | **label problem** — no code fix |
| B | 162 | **not a failure** — the operating point |

**Zero are "one bug".** Worth stating because it is the answer §6.3 wants and because it
would be suspicious unchecked: I looked for a single defect behind several failures and did
not find one. The bugs that did exist were found earlier and by other means — the operating
curve reading the wrong field, and two lanes that killed a line instead of passing it on —
and none appears here because each was fixed before it could produce a failure.

---

## 4. The label problem

§6.4 asks for at least three lines where the label is wrong or the task under-specified.
Here is the systematic version rather than three anecdotes.

**102 train lines are an exact, unique match to one active catalogue item** after
normalisation — the least ambiguous input the task contains.

| | n | share |
|---|---|---|
| labelled with that exact code | 71 | 69.6% |
| **labelled blank** | **31** | **30.4%** |

**The same input pattern carries both labels.** No decision procedure can satisfy both
populations. Two lines make it concrete:

```
ACM-T-0001  'Tolsen Wall Plug 12mm Red'          -> labelled ACM-WALL0029
ACM-T-0015  '- Hitex Angle Grinder Disc 7" Flap' -> labelled blank
```

Both are byte-identical to a unique active item. One is an answer; one is not.

**Nine of the 31 are explained, and the explanation is real signal.** Where the matched item
has a `(Bulk)` sibling — an `XB` code sharing its name, its barcode and often its
`stock_uom` — the line is labelled blank **90%** of the time (9/10) against **23.9%** (22/92)
where it does not. That is a genuine rule: an exact match is not an answer when a pack
variant makes it ambiguous. It is also a trap the brief does not mention.

**Twenty-two are not explained by anything measurable.** Checked and ruled out:
`available_qty` (49 labelled answers point at qty=0 items), `disabled`, `list_price`,
`stock_uom`, `item_group`, `brand`, `customer_id`, `channel`, and whether the catalogue name
was genuinely unique. Nothing separates the 22 from the 71.

**Six named lines**, well past the three asked for: `ACM-T-0015`, `ACM-T-0050`, `ACM-T-0055`,
`ACM-T-0198`, `ACM-T-0212` (each byte-identical to a unique active item, labelled blank) and
`ACM-T-0209` (labelled the `(Bulk)` variant with no bulk token anywhere in the line).

### The consequence, which is a design constraint rather than a complaint

"Answer an exact unique name match" scores **69.6%**, or 76.1% excluding `(Bulk)` pairs. Both
far below break-even. **An obviously correct rule cannot ship.** The matcher abstains on most
exact matches, which reads as over-caution until you see this table.

### What I would do in production

**Nothing unilateral, and that is the point.** We are scored against their key, so the
shipped matcher follows the labels and the disagreement is reported with the evidence. In a
real deployment:

1. **Re-label the 102 with a second annotator** and measure inter-annotator agreement. If it
   is ~70% on the *least* ambiguous population, the ceiling is the annotation guideline, not
   the model, and no amount of engineering moves it.
2. **Ask the one question that would resolve the `(Bulk)` half.** When a buyer names an item
   with no pack qualifier, is the non-bulk variant the intended default? That recovers ~25
   items per tenant if answered and should not be guessed from two examples. Filed in
   `_work/QUESTIONS.md`.
3. **Treat the remaining 22 as a labelling defect, not a modelling target.** Fitting them
   means fitting noise, and at 20× the wrong direction is expensive.

---

## 5. Regression safety

§6.5 asks how this harness stops a bad change, concretely, and how the benchmark is kept from
rotting. The answer is 94 tests in four tiers, and two of them are unusual.

### What breaks the build

| tier | guards | examples |
|---|---|---|
| **T-C contract** | malformed or non-deterministic output | schema, determinism, field domains, closed reason-code set, **p95 ≤ 250 ms**, tenant isolation |
| **T-A trap** | a confirmed trap regresses | one test per trap, each named for its mechanism |
| **T-D document** | a `.md` quotes a number the code no longer produces | the calibration staleness guard |
| **T-W walkthrough** | *I* cannot re-derive my own decision | human, not automatable |

**Hard gates.** Any cross-tenant answer *or candidate* fails (§5.4 makes it fatal). p95 above
250 ms fails. Non-determinism fails. An unregistered `reason_code` fails, because a reason
nobody can look up is not an explanation. `python3 -m src.predict --check` validates the
delivered CSV itself, not the objects that produced it — a schema the code satisfies and the
file does not is still a failure.

### The two that matter most

**Mutation-checked isolation.** A test that cannot fail is not a control. Disabling *only* the
supersession redirect fails exactly the two T-A3 tests and nothing else; inflating one
published confidence from 0.9556 to 0.9900 fails exactly the staleness guard. Both verified
by running them.

**The staleness guard is the anti-rot mechanism.** `CALIBRATION` is a committed constant
quoted in this document. `test_the_committed_table_matches_a_fresh_measurement` re-measures
and diffs, so changing the matcher without re-running the generator **fails the build** rather
than leaving the submission quoting a confidence it no longer earns. **A committed constant
that has drifted from what the code does is worse than no constant, because it carries the
authority of a measurement.** The same discipline is what §6.5 is asking about, applied to a
number in the source rather than in prose.

### How a bad change actually gets caught

A change that raises coverage by loosening the margin gate does not fail a test — it is not
illegal, it is just worse. It is caught by the harness printing **net value against the null
matcher** on every run. That single number is the gate a human reads, and it is why the null
matcher is a permanent fixture rather than a bootstrapping convenience: **"beats zero" and
"beats doing nothing" are different claims, and only one of them matters.**

### What this does not protect against

Three things, stated because a regression story that claims completeness is not credible:

- **Train-set overfitting.** Every threshold here is chosen on 420 lines. The harness cannot
  detect that; only the holdout can.
- **A change that improves train and harms holdout** in a way no test encodes — the
  `source != manual_import` gate would have passed everything and been wrong (D-05).
- **Label drift.** If the graders' key disagrees with train the way train disagrees with
  itself (§4), the harness will confidently report the wrong thing. That is the risk this
  submission is most exposed to, and it is unmitigable from here.
