# Question Bank — questions only, deliberately unanswered

**Why answers are not here yet.** A question written down is testable: it either turns out
to be real, or it dissolves once the data is understood. Writing the answer at the same time
hides which of the two happened. So this file collects questions first; answers are drafted
only in §4, and only after the relevant phase is done.

Three buckets:

- **§1 Ask Mindhive** — §11 of the brief: *"Questions are allowed at any point during the
  3 days. Asking a sharp one is a positive signal; we will note it."* This is scored. It is
  the one bucket with a deadline, since a question sent on day 3 is worth little.
- **§2 They ask us** — the 20-minute "we drive" segment (§12).
- **§3 Live change** — the 20-minute "modify your code with us watching" segment (§12).

Status: `[ ]` open · `[?]` may dissolve, recheck after the phase · `[x]` resolved, answer in §4
· `[→]` sent to Mindhive

---

## 1. Questions to ask Mindhive

Filter before sending: a question already answered by the data is a **negative** signal.
Each is tagged with the phase that must complete first, so nothing is sent prematurely.

### 1a. About the objective function

- `[ ]` The 20x ratio is stated as "roughly". Is it 20x in **operator time**, or 20x in
  **money** including the credit note and the churn risk? The two give different operating
  points, and §4.1 asks who may move it.
- `[ ]` The brief says some wrong matches are never caught and "quietly corrupt the alias
  table". Should the undetected-corruption cost be inside the 20x, or is 20x the
  *caught*-error cost with contamination on top? *(after P1)*
- `[ ]` Is the 40 s abstention cost flat, or does a reviewer handed a good `candidates` list
  cost materially less than one handed nothing? If the latter, recall@3 is worth optimising
  directly rather than reporting.

### 1b. About the data — only after probing, so as not to ask what is answerable

- `[?]` `customer_sku_map.confidence` takes exactly three values (1.0 / 0.72 / 0.55) and, on
  train, precision at 1.0 is **22.6%** while 0.55 is **100%**. Is the column a deliberate
  decoy, a real production artefact, or generator noise? *(TR-02; after P3 — asking this
  well requires our own numbers attached)*
- `[?]` `-OLD` supersession: is redirecting an alias to the active successor the intended
  production behaviour, or should the system abstain and ask the buyer to update their SKU?
  The label says redirect; a real distributor might prefer the abstention. *(TR-01)*
- `[?]` Nordic is ~89% twin items by pack size. Is that representative of the real frozen
  food catalogue, or an artefact of generation? It decides how much of the design should
  bend around size arbitration. *(TR-04; after P3)*
- `[ ]` `notes` on some lines reads `"price quoted per outer"`. Is `notes` a field the
  production matcher receives, or an operator annotation added after the fact? If the
  latter, using it is leakage.

### 1c. About scope

- `[ ]` "Service-shaped" (§5.1) — is a library with a single documented entry point
  sufficient, or is a runnable HTTP surface expected? *(cheap to ask, expensive to guess
  wrong: it is the difference between ~0 h and ~2 h)*
- `[ ]` `predictions.csv` requires one row per holdout line. For a line that is not an item
  at all, is `reject` versus `review` a distinction that is scored, or are both simply
  "not auto"?

---

## 2. Questions they are likely to ask us

Drawn from what the brief says it grades, plus the places our own approach is soft.

### 2a. On framing (§12, first 10 minutes — "the problem, not your code")

- `[ ]` State the objective function. What are you maximising, subject to what?
- `[ ]` Who in the business is allowed to move the operating point, and what would make them?
- `[ ]` §4 asks whether "the expensive mistakes and the common mistakes are different
  populations". Are they, on this data? Show it.
- `[ ]` Where does "I don't know" live in your design, and why is it not an afterthought?

### 2b. On the numbers

- `[ ]` Your precision is X% at Y% coverage. Why that point and not 10 points either side?
- `[ ]` What is your net value under the cost model, and what does the null matcher
  (abstain on everything) score? If you cannot beat it, why ship?
- `[ ]` How is `confidence` comparable across lanes when the lanes are different mechanisms?
- `[ ]` Which of your reported numbers would change most if we reran on a different sample?

### 2c. On the traps

- `[ ]` What did you find that the brief did not tell you about? *(TR-01, TR-02, TR-06)*
- `[ ]` The brief says buyer SKUs can look like another tenant's codes. Did you find any?
  *(TR-09 — refuted; the interesting answer is that we kept the control anyway, and why)*
- `[ ]` You gated on `source != manual_import`. Is that causal or a confound?
  *(the trap in our own reasoning — see TR-02's note)*
- `[ ]` Show us a label you think is wrong and argue it.

### 2d. On what was skipped

- `[ ]` You did not build X. What would you have learned from it?
- `[ ]` If you had one more day, what is the first thing you would do, and why is it that
  and not the second thing?
- `[ ]` Which part of your submission are you least confident about?

---

## 3. Live-change scenarios to prepare for

§12 gives 20 minutes with them watching. The rehearsal target is **naming the file and
function within 30 seconds**, then making the change. Each of these is also a design
constraint: if a scenario has no single obvious home in the code, that is a finding about
the architecture, not about the scenario.

- `[ ]` **Cost ratio changes 20x → 3x.** Which thresholds move, which direction, how far?
  The interesting answer is whether the operating point is one constant or scattered.
- `[ ]` **New noise pattern**, e.g. buyers start writing `4inch` for `4"`, or Malay plurals,
  or a new trade abbreviation. Where does normalisation live?
- `[ ]` **A new tenant arrives with zero alias history.** Does behaviour change on its own,
  or does someone have to configure it? §5.1 requires the behaviour to differ *and* to be
  explained.
- `[ ]` **Coverage must rise 10 points by Friday** without precision dropping. What is the
  next lever, and what does it cost?
- `[ ]` **A `reason_code` must be split** because ops cannot triage one bucket. How much
  else moves?
- `[ ]` **Tenant isolation must extend to per-customer isolation.** Is the boundary a
  parameter or a hardcode?
- `[ ]` **Task 4:** the report owner wants p99 as well as p95. Does the rewrite absorb it?
- `[ ]` **Task 5:** the ERP raises its idempotency window from 60 s to 5 s. What breaks?

---

## 4. Answers — populated later, per phase

Empty by design. An entry moves here only when its phase is complete and the answer is
backed by a number or a test, so that the gap between "what I assumed on day 1" and "what
turned out to be true" stays visible rather than being edited away.

| Q | Phase | Answer | Evidence |
|---|---|---|---|
| — | — | — | — |
