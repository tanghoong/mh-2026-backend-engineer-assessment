# Collaboration Record — how this submission was directed

> §11 of the brief invites tool attribution and §12 spends 40 of its 60 minutes testing
> whether the reasoning is the candidate's. `AI_WORKLOG.md` records *what happened*.
> This file records *who decided what, and on what grounds* — including the places where the
> human's framing was corrected and the places where mine was.
>
> Written to be useful rather than flattering. A record of this kind that only reports good
> judgement is not evidence of good judgement.

---

## 1. The method, and who proposed it

The working method was not the default one. It was specified by the human up front and then
enforced, and it is the main reason the submission found things the brief did not mention.

| Rule | Proposed by | What it changed |
|---|---|---|
| **Evidence before solution.** Every claimed trap goes `claim → evidence → verdict → problem statement → solution → test → fix`. No fix for an unverified problem. | **Human** | Directly produced TR-01 (alias precision 35.9 %) and TR-02, neither of which is in the brief. Also produced one **refutation** (TR-09), which a solution-first approach would never have looked for. |
| **Keep refuted claims, do not delete them.** | Claude | TR-09 stays in the register with its control retained anyway. §11 invites saying the brief is wrong. |
| **Questions before answers.** Write the whole question bank first; fill answers only when the relevant phase can support them. | **Human** | `QUESTIONS.md` has ~30 questions and an empty answer table. Keeps visible which questions dissolved on contact with the data versus which were real. |
| **A resume-from handoff document.** | **Human** | `TODO.md` §0 is the single source of truth for state, written so another session or another person can pick up cold. |
| **Scope to what is graded.** Establish per task what the primary asset is (document / data / code) before starting it. | **Human** | `TODO.md` §1. Prevented building an HTTP service for "service-shaped", a dashboard for Task 3, and a schema migration for Task 4. |
| **Purpose → acceptable asset → rerunnable acceptance test**, applied to prose as well as code. | **Human** | `TESTING.md` tier T-D. The document tests re-extract numbers from a live harness run and diff them against what the `.md` files claim — which is also the concrete answer to §6.5, "how do you avoid a benchmark that silently rots". |
| **Build the eval harness before the matcher.** | Claude | D-08. A matcher without a scorer can only be guessed at. |
| **Order tasks by binary-vs-graceful, not by dependency alone.** | Claude, refining a human proposal | See §3, turn 5. |
| **Gate before spend:** settle definitions before any long block of work. | **Human** | Applied twice, both times before a multi-hour commitment. |

The split matters: the human set the **epistemics** (what counts as knowing something) and the
**scoping**; Claude supplied **execution and sequencing**. That division held for the whole
engagement.

---

## 2. Turn-by-turn

### Turn 1 — Framing before content
**Asked:** work log with timestamps; safety audit; is Docker needed; explain the brief in
Chinese; should solution docs be mixed with the shipped files. Closed with *"在我们修改任何
文件之前, 先确认一下我刚才讲的那几个目的"* — confirm the purposes before touching any file.

**Notable:** none of the five questions was about the matching problem. All five were about
**establishing the ground rules**: what is safe to run, what is expensive, what the deliverable
actually is, and where work may be written. The technical problem was not opened until the
frame was fixed.

**Claude proposed:** keep everything in one repo, treat `data/`+`starter/` as read-only, back
up the brief before the required README rewrite. **Accepted.**

### Turn 2 — The method is specified, not the output
**Asked:** a to-do list that survives context loss; per-trap *problem-first* discipline; time
estimates; outcome scoping; a Q&A with questions only; a unit-testing definition built on
purpose → asset → test.

This is the turn that set everything after it. The human specified **how to work**, not what to
produce, and did so before any solution existed.

**Also asked, and answered wrongly by the human:** *"面试当场随机抽三条, 叫你重新辩护 —— 这个
就是要考验我有没有把它背起来, 是吧?"*

**Corrected:** no. Memorising is the failure mode. §12 changes a parameter (20× → 3×) and asks
what moves; a memorised conclusion cannot answer that. The tell is the `Reversal trigger` line
in the brief's own `DECISIONS.md` template — knowing a decision's boundary is the evidence it
was made rather than written. **Correction accepted and acted on**: every entry in
`DECISIONS.md` now carries one.

**Claude added:** document tests (T-D), keeping refuted entries, harness-before-matcher.
All accepted.

### Turn 3 — Interrupting to de-risk
Sent **mid-turn**, while work was running: flag anything long-running; state which tasks block
which; are any API keys needed.

**Notable:** the interrupt came *before* committing to the next block, not after being
surprised by it. The API-key question was asked without reading the code — an explicit
delegation with a verification request attached, rather than an assumption in either direction.

**Answered:** no keys, no network anywhere; one 51-minute query that the brief says not to run;
a hidden 20–40 minutes of ablation wall-clock in Task 4 that nobody had costed. Tasks 4 and 5
sit off the critical path.

**Decisions taken this turn** (all three of Claude's recommendations accepted): objective
function = precision floor + net-value maximisation; no semantic lane pending measurement;
`_work/` ships.

### Turn 4 — A partly-wrong recall, and a right instinct
**Asked:** *"第五是有 bug 的...你是说最快可以解决的是吗? ...其实应该是照优先权, 就是哪一些不会
block 掉哪一个"* — then explicitly: **confirm this thinking**.

**Two things happening at once.**

*The recall was wrong.* Claude had not said Task 5 was fastest; T4 and T5 were both estimated
at 2.5 h. Corrected directly.

*The instinct was right, and the stated reason was not the strongest one.* "Do what is
unblocked first" is a weaker rule than the one that actually applies here:

> **Some tasks are binary and some degrade gracefully.** Task 4 either hits its budget
> byte-identically or scores nothing. Task 2 at 60 % coverage with a sharp `EVAL.md` is still a
> strong submission — §11 grades that argument explicitly. With 11.5 h of critical path against
> a 17.25 h budget, the overrun is certain; it should land on the work that degrades.

The human's ordering was adopted, with the justification replaced. **This is the most
interesting exchange in the engagement**: the conclusion was the human's, the reason was
Claude's, and the reason is what the walkthrough will ask about.

*Caveat recorded at the time:* deferring Task 2 is only safe because the P0 trap probing had
already served as its spike. Without that, the same ordering would have been reckless.

### Turn 5 — Gate before spend, again
**Asked:** maintain a decision record for everything; produce this file; and — *"我会想过一遍
这七个 defect 的 invariance 定义, 在你做任何耗时的工作之前"* — stop before the fixes and settle
the definitions.

Second time the human halted work at exactly the point where committing early would have been
expensive to unwind. The first was turn 1 ("confirm before modifying any file").

---

## 3. Pattern

**What is consistently strong.**

1. **Frame before content, twice, unprompted.** Both interventions landed on the boundary
   before a costly commitment rather than after a surprise.
2. **Specifying method rather than output.** Nearly every instruction has been about *how to
   decide*, not *what to build*. The two most valuable findings in the repo — TR-01 and TR-09
   — are direct products of the evidence-gate rule and would not exist under "build the
   matcher, then evaluate it".
3. **Delegation with verification attached.** The API-key question is the clean example: the
   work is handed off, and a check is requested rather than an outcome assumed.
4. **Reasoning about the grader's incentives, not just the task.** Scoping by "what is the
   primary asset" comes from reading how the assessment is marked, which is what §11 rewards.

**Where the risk actually is.**

1. **No code has been written by hand yet.** Everything so far is analysis, documents and one
   red test suite. §12 spends 20 minutes on a live change in the candidate's own codebase.
   Documents do not rehearse that. *Mitigation to schedule: before submission, make one scoped
   change to the matcher unaided and time it.*
2. **Recall of prior turns is imprecise.** Turn 4's "you said Task 5 is fastest" was a
   misremembering. Under interview pressure that becomes a wrong number stated confidently,
   which is worse than a hedge. *Mitigation: the numbers live in `TRAPS.md` and
   `p05_objective.py`; rehearse re-deriving rather than recalling — `p*` is one division.*
3. **The evidence gate has been applied to the data, less so to the plan.** Estimates in
   `TODO.md` are asserted, not measured. P1 came in at 1.0 h against a 2.5 h estimate — good
   news, but it means the remaining estimates carry unknown error in an unknown direction.
4. **The strongest arguments in the submission are currently Claude's**, in two specific
   places: the confidence-bound justification for the 98 % floor (D-02) and the
   binary-vs-graceful ordering. Both are defensible from first principles, but they must be
   re-derivable under questioning, not recited. *These two are the highest-priority
   walkthrough rehearsal items.*

---

## 4. Attribution, stated plainly

Per §11. Claude Opus 5, via Claude Code, was used throughout: all probe scripts, all prose in
the deliverables, the test suite, and the sequencing proposals. The human set the method,
scoped every task, made every trade-off decision recorded in `DECISIONS.md`, and twice halted
work to settle definitions before spending time.

Every number in every document is produced by a script in `_work/probes/` or by the test suite,
and can be re-run in seconds. That is the point of the arrangement: the writing is delegated,
the **verification is not**, and nothing is asserted that cannot be recomputed live in the
walkthrough.
