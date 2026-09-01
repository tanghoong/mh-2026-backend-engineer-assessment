# SYNC — Task 5

> **STATUS: defects found and isolated; invariants defined; fixes not yet applied.**
> The 7 tests in `tests/sync/` are committed **red** at `b7221f9`, each failing on its own
> assertion. Fixes land after the invariants below are agreed, so that every change can be
> justified by the property it restores rather than by the symptom it silenced.

`fake_erp.py` is unmodified and will stay that way. Its awkward semantics — second-resolution
cursors, non-transactional batches, 504-after-commit, exact-match idempotency, server-local
timestamps — are the environment, not the bug.

---

## 1. Defect list

7 defects. 3 explain the open tickets; 4 have not produced one yet.

| ID | Ticket | Mechanism | Test |
|---|---|---|---|
| D1 | MAIA-812 | Cursor stores `page[-1].updated_at` at second resolution; `list_changes` filters on strict `>`. A record tied with the last row of a page is skipped **permanently**. | `test_d1_cursor_tie_at_page_boundary_drops_records` |
| D2 | MAIA-830 | `idempotency_key` hashes `attempt`, so a retry can never present the same key and the exact-match window never fires. It also hashes `time.time()`. | `test_d2_retry_after_a_504_writes_twice` |
| D3 | MAIA-844 | The `ErpConflict` handler refetches `version` but not `payload`, converting a 409 into permission to overwrite. | `test_d3_conflict_handler_overwrites_the_remote_edit` |
| D4 | — | The cursor advances **before** the page is applied. | `test_d4_cursor_advances_before_the_page_is_applied` |
| D5 | — | `pull` overwrites a dirty local record with `dirty=False`. | `test_d5_pull_silently_discards_an_unsent_local_edit` |
| D6 | — | The write inside the `ErpConflict` handler is unguarded. | `test_d6_a_504_inside_the_conflict_handler_aborts_the_whole_sync` |
| D7 | — | Server-local `+08:00` timestamps are stored in a field named `updated_at_utc`. | `test_d7_server_local_timestamps_are_stored_in_a_field_named_utc` |

**Evidence.** All three ticket symptoms reproduce deterministically from
`python3 run_sync.py`. In the seeded 60-record batch, **16 timestamps are shared by more than
one record** (one is shared by 6), and records 50 and 51 both carry `2026-08-01 00:00:58` —
exactly straddling the 50-row page boundary, which is why `EXT-0050` is the one that vanishes.

**On D2's second term.** `time.time()` in the hash fails *non-deterministically*, and this
machine hides it: Windows' clock resolution is **15.625 ms**, so two back-to-back calls return
the same value and the key looks stable. On Linux (nanosecond resolution) it would not. A
defect whose visibility depends on the developer's clock is worse than one that always fires,
because the reproduction attempt is what fails.

---

## 2. Invariants — the properties each fix must restore

Stated before the fixes, so that each change is judged against a property rather than against
the symptom that revealed it. An invariant that only holds in the tested scenario is not an
invariant.

### I-1 — The cursor never advances past a timestamp group that has not been fully drained
> *Restores D1. At every point, no record with `updated_at <= cursor` is unapplied.*

The cursor's real job is to identify a **resumption point**, and a second-resolution timestamp
cannot do that when ties exist. The vendor API only accepts `since` as a string compared with
`>`, so a composite `(updated_at, external_id)` cursor is not available server-side.

The fix is therefore to **advance only to the last timestamp whose group is complete**: drop
the trailing partial second from the page and stop the cursor before it.

**Known edge case this creates:** if a single timestamp holds more records than `page_size`,
the cursor can never advance and the pull loops forever. That has to be handled explicitly —
detect a page that is entirely one timestamp, and either raise the limit for that call or
fall back to overlap-and-deduplicate. Naming this now matters more than the code: it is the
failure the naive version of this fix introduces.

*Rejected alternative:* rewind the cursor by one second and re-read. Simpler, but it makes
every cycle re-deliver records and only works if apply is idempotent — which it is, but that
turns a correctness property into a performance tax paid forever.

### I-2 — One logical local edit produces at most one remote write
> *Restores D2. The observable property; key stability is the mechanism.*

The Idempotency-Key must be a pure function of the **local change identity** — `external_id`
plus payload plus a local revision — and must not contain the retry counter or a clock. It
must also be **generated once and persisted before the first attempt**, so that a process
killed mid-retry presents the same key on restart. A key regenerated after a crash is a new
key, and the whole guarantee is gone.

**What this invariant cannot cover.** `fake_erp.py`'s docstring promises the key is "honoured
for 60 seconds", but `_idem` is a plain dict with **no TTL** — the stub does not implement its
own documented expiry. So the path where a retry arrives after the window closes is not
reachable by any test we can write against this vendor. That is a finding, not a coverage gap,
and it goes in §4 as the first thing to ask the vendor for.

### I-3 — No write is based on remote state we have not read
> *Restores D3. A 409 is never resolved by discarding the other side.*

The current handler treats the 409 as a version problem. It is not: it is the ERP saying
*someone else changed this row*. Refetching the version and re-writing our payload is a
compare-and-set that deliberately ignores what it compared against.

**The resolution policy is a business decision, not a technical one** — see the open question
in §5. The proposed default is **detect, do not overwrite, record, leave dirty**: preserve both
sides and make the conflict visible, rather than choosing a winner silently.

The asymmetry that justifies it is the same one as in `DESIGN.md` §1. Not pushing our edit is
*recoverable* loss — the edit is still local and still flagged. Overwriting their edit is
*unrecoverable* — it is gone from both systems. Two failure modes with very different costs
should not be resolved by whichever process happened to run last.

### I-4 — The cursor is durable only after the work it covers is durable
> *Restores D4. At every observable point, `cursor <= updated_at` of the last record durably applied.*

Apply the page, commit, then advance the cursor. A crash in between causes re-delivery, which
is harmless **because apply is idempotent by `external_id`** — that idempotence is a
precondition of this fix, not an incidental property, so it is asserted rather than assumed.

Note this invariant makes the system **at-least-once**, deliberately. At-most-once would
require the cursor to move first, which is what D4 already does and what loses records.

### I-5 — `pull` never clears the `dirty` flag on a record it did not push
> *Restores D5. An unsent local edit is never discarded without being recorded.*

Deliberately stated as a rule about the flag, not about timestamps. The existing guard tries
to decide who is newer and **fails open** — when the comparison does not fire, it clobbers.
Any invariant phrased as "the newer one wins" inherits that failure mode and also depends on
D7 being fixed first, which would make one fix repair two defects.

Phrasing it as a flag rule makes it independent, mechanical, and true regardless of clocks.

### I-6 — A transient failure on one record never affects another
> *Restores D6. No per-record exception escapes `push`; every dirty record is attempted once per cycle.*

Fault isolation per record. On exhaustion the record stays dirty, the error is recorded, and
the loop continues. The current code has this property on the first write and loses it on the
retry inside the conflict handler — the guard exists, it is just in one of the two places that
needs it.

### I-7 — A timestamp's zone is part of its type
> *Restores D7. `updated_at_utc` holds UTC only; the cursor holds server-local only; neither is ever assigned to the other.*

The subtlety worth stating explicitly: **this is not "convert everything to UTC".** The cursor
*must* stay in the ERP's local zone, because `list_changes` compares it as a string against
server-stamped values. So the system legitimately has two clocks, and the fix is to name them
apart and never cross them — `cursor_server_local` and `updated_at_utc` — rather than to pick
one and normalise.

Converting the cursor to UTC would be a correct-looking change that breaks pagination
silently, which is why the invariant is about typing rather than about a canonical zone.

---

## 3. Fixes

*Pending — applied after the invariants above are agreed.*

## 4. The contract I wish I had

*Pending. First item is already established: the vendor's own stub does not implement the
60-second idempotency TTL it documents, so its actual expiry behaviour is unspecified and
untestable from the outside.*

## 5. Open question

**D3's conflict-resolution policy.** Three defensible options, and the choice belongs to the
business, not to the adapter:

| Option | Behaviour | Cost |
|---|---|---|
| **Abstain and flag** *(proposed)* | Detect, write nothing, keep dirty, surface for review | Local edit is delayed, possibly indefinitely, if nobody works the queue |
| Field-level merge | Apply our changed fields onto the remote payload | Requires knowing which fields we actually changed; silently wrong if two sides changed the same field |
| Newest-timestamp wins | Compare `updated_at` and let the later one win | Depends on two clocks agreeing (see I-7), and still discards one side silently |

## 6. What breaks at scale

*Pending.*
