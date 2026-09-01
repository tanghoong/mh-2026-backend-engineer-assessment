# SYNC — Task 5

> **STATUS: complete.** 7 defects isolated, 7 invariants defined, fixes applied, 7/7 green.
> The tests were committed **red first** at `b7221f9` and the fixes in a later commit, so the
> history shows each test failing on its own assertion before the repair rather than being
> written to fit it.

`fake_erp.py` is unmodified. Its awkward semantics — second-resolution cursors,
non-transactional batches, 504-after-commit, exact-match idempotency, server-local timestamps
— are the environment, not the bug.

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

**When each latent defect would surface**

| | Condition required in production |
|---|---|
| D4 | The process is killed mid-page — a deploy restart or an OOM during a large initial sync. Everything between the cursor and the last commit is lost, permanently. |
| D5 | A remote touch lands between a local edit and the next push. At a 5-minute cadence across 500 tenants that window is open most of the time. |
| D6 | A 409 and a 504 on the same record in the same attempt. At a 15 % timeout rate that is a daily event; it presents as "sync just stops sometimes", which is why it has no ticket of its own. |
| D7 | The first piece of code that compares a stored timestamp against `now_utc()`. Nothing does today, so the skew is dormant rather than absent. |

**On D2's second term.** `time.time()` in the hash fails *non-deterministically*, and this
machine hides it: Windows' clock resolution is **15.625 ms**, so two back-to-back calls return
the same value and the key looks stable. On Linux (nanosecond resolution) it would not. A
defect whose visibility depends on the developer's clock is worse than one that always fires,
because the reproduction attempt is what fails.

---

## 2. Invariants — the property each fix restores

Stated before the fixes were written, so each change is judged against a property rather than
against the symptom that revealed it. An invariant that only holds in the tested scenario is
not an invariant.

### I-1 — The cursor never advances past a timestamp group that has not been fully drained
> *Restores D1. At every point, no record with `updated_at <= cursor` is unapplied.*

The cursor's job is to identify a **resumption point**, and a second-resolution timestamp
cannot do that when ties exist. The vendor API accepts `since` only as a string compared with
`>`, so a composite `(updated_at, external_id)` cursor is not available server-side.

The fix is to **advance only to the last timestamp whose group is complete**: drop the trailing
partial second from a full page and stop the cursor before it.

**The edge case this fix introduces:** if a single timestamp holds more records than
`page_size`, the trimmed batch is empty, the cursor never advances, and the pull loops forever.
Handled explicitly by `_drain_timestamp_group`. Naming this mattered more than the code — it is
the failure the naive version of this fix creates, and it is worse than the one it repairs.

*Rejected alternative:* rewind the cursor by one second and re-read. Simpler, but it makes every
cycle re-deliver records and turns a one-off correctness fix into a permanent tax.

### I-2 — One logical local edit produces at most one remote write
> *Restores D2. The observable property; key stability is the mechanism.*

The Idempotency-Key must be a pure function of the **local change identity** — `external_id`,
payload, local revision — with no retry counter and no clock. It must also be **minted once and
persisted before the first attempt**, so a process killed mid-retry presents the same key on
restart. A key regenerated after a crash is a new key and the guarantee is gone.

**What this invariant cannot cover.** `fake_erp.py` documents that the key is "honoured for 60
seconds", but `_idem` is a plain dict with **no TTL** — the stub does not implement its own
documented expiry. The path where a retry arrives after the window closes is therefore
unreachable by any test we can write against this vendor. That is a finding, not a coverage
gap; it is item 2 in §4.

### I-3 — No write is based on remote state we have not read
> *Restores D3. A 409 is never resolved by discarding the other side.*

The old handler treated the 409 as a version problem. It is not: it is the ERP saying *someone
else changed this row*. Refetching the version and rewriting our payload is a compare-and-set
that deliberately ignores what it compared against. The resolution policy is a business
decision — see §5.

### I-4 — The cursor is durable only after the work it covers is durable
> *Restores D4. At every observable point, `cursor <= updated_at` of the last record durably applied.*

Apply the page, commit, then advance the cursor. A crash in between causes re-delivery, which
is harmless **because `_apply` is idempotent on `external_id`** — that idempotence is a
precondition of this ordering, not an incidental property, so it is asserted rather than
assumed. This makes the system **at-least-once, deliberately**. At-most-once is what the old
ordering bought, and it paid for it with the records it dropped.

### I-5 — `pull` never clears the `dirty` flag on a record it did not push
> *Restores D5. An unsent local edit is never discarded without being recorded.*

Deliberately a rule about the flag, not about timestamps. The old guard tried to decide who was
newer and **failed open** — when the comparison did not fire, it clobbered. Any invariant
phrased as "the newer one wins" inherits that failure mode *and* depends on I-7 being fixed
first, which would make one change repair two defects — exactly what §8.1 marks down.

### I-6 — A transient failure on one record never affects another
> *Restores D6. No per-record exception escapes `push`; every dirty record is attempted once per cycle.*

Fault isolation per record. On exhaustion the record stays dirty, the error is recorded, the
loop continues. The old code had this property on the first write and lost it on the retry
inside the conflict handler — the guard existed, it was just in one of the two places that
needed it.

### I-7 — A timestamp's zone is part of its type
> *Restores D7. `updated_at_utc` holds UTC only; the cursor holds server-local only; neither is ever assigned to the other.*

**This is not "convert everything to UTC".** The cursor *must* stay in the ERP's zone, because
`list_changes` compares it as a string against server-stamped values. The system legitimately
has two clocks; the fix is to name them apart — `cursor_server_local` and `updated_at_utc` —
and never cross them. Converting the cursor to UTC would be a correct-looking change that
breaks pagination silently, which is why the invariant is about typing rather than about
picking a canonical zone.

---

## 3. Fixes

Applied to `starter/sync/sync_adapter.py`; `fake_erp.py` untouched. Every change carries an
`(I-n)` marker in the source pointing back at §2.

| Invariant | Change |
|---|---|
| I-1 | `pull` trims the trailing timestamp group from a full page instead of consuming it. `_drain_timestamp_group` handles the case that trimming introduces. |
| I-2 | `idempotency_key(external_id, payload, local_revision)` — `attempt` and `time.time()` removed. Minted once per dirty episode, stored on the record before the first attempt, reused by every retry, cleared on success. |
| I-3 | The `ErpConflict` handler reads the remote **payload**, records a `Conflict`, writes nothing. |
| I-4 | `set_cursor` moved to after the batch is applied. |
| I-5 | `_apply` refuses to overwrite any `dirty` record and records a conflict instead. |
| I-6 | `_push_one` never raises; both write paths guarded, exhausted attempts recorded, loop continues. |
| I-7 | `server_local_to_utc` at ingress; `updated_at_utc` holds UTC, `remote_updated_at_server` holds the raw string, `cursor_server_local` is named for its zone. |

### Evidence

`python3 run_sync.py`, before and after:

```
before:  pulled=59 pushed=3 remote=60 local=59
         INV1 missing locally: 1 records e.g. ['EXT-0050']
         INV2 duplicate writes: {'EXT-0042': 2}
         INV3 remote edit clobbered: EXT-0011 payload is {... 'uom': 'Nos'}

after:   pulled=60 pushed=2 remote=60 local=60
         INV1 version drift: 1 records e.g. ['EXT-0011']
```

**The remaining line is the fix working, not a regression.** `EXT-0011` is the record with a
genuine conflict, and the adapter now refuses to resolve it:

```
CONFLICT EXT-0011
  reason        : remote_changed_while_local_edit_pending
  our version   : v1   payload={'name': 'item 11', 'price': 999.0, 'uom': 'Nos'}
  their version : v2   payload={'name': 'item 11', 'price': 55.5, 'uom': 'Box'}
```

`run_sync.py`'s INV1 asserts that every record converges to the remote version, which is only
true of an adapter that silently picks a winner — the behaviour MAIA-844 was raised about. The
symptom reporter has no vocabulary for *correctly unresolved*, which is why §8.1 asks for it to
be replaced rather than extended. `pushed` falling from 3 to 2 has the same cause: the third
write was the one that destroyed a remote edit.

### What I did not fix

- **`local_revision` is never incremented.** Nothing in this harness edits through a helper, so
  the field exists and stays 0. Consequence: edit → push → revert-to-original → push produces
  the same key twice, and inside the vendor's window the second push is swallowed. The fix
  belongs at the edit site, not in the adapter.
- **`idem_key` is held in memory.** I-2 requires durability before the first attempt; in a real
  store it is a column written in the same transaction that sets `dirty`.
- **Conflicts accumulate with no expiry and no resolution path.** The deliberate cost of the §5
  policy, and the first thing that needs an owner in production — see §6.

## 4. The contract I wish I had

Priority order, with how we stay correct while the vendor says no.

**1. A continuation token that is not a timestamp.** Opaque, totally ordered, no ties. Every
part of I-1 exists only because the cursor is a second-resolution timestamp compared with a
strict `>`. Second best: sub-second resolution plus a documented tiebreak on `external_id`.
*At "no":* drain the trailing group, as implemented — correct, but it makes the client re-derive
pagination state the server already holds, and it degrades badly on bulk imports (§6).

**2. A way to ask whether a write landed**, e.g. `GET /writes/{idempotency_key}` — and
**implement the documented TTL**. A 504 after commit is unresolvable ambiguity today: the
response says nothing about the write, so the only safe retry is one the server recognises.
Meanwhile the stub's `_idem` has no expiry at all, so the post-window behaviour is both
unspecified and untestable from outside. *At "no":* persist the key, retry within the window,
and after it re-read the record and compare payload and version before writing again — a read
which is itself racy. There is no clean answer without the vendor.

**3. The current record in the body of the 409.** We refetch after the conflict, and the row can
change between the 409 and the GET, so a recorded conflict may already be stale. *At "no":*
accept it and treat the recorded payload as evidence rather than truth — whoever resolves the
conflict re-reads before acting.

**4. Timestamps with an offset.** ISO 8601 with the zone attached. *At "no":* pin the offset in
configuration and assert it at ingress. We are lucky that +08:00 does not observe DST; the same
code against a DST-observing server would be right for half the year and wrong for the other
half, which is the worst available failure mode.

**5. Per-record results for a batch write.** A batch is not transactional and reports one
outcome. *At "no":* one record per call, and pay the throughput.

## 5. Conflict resolution policy

**Chosen: detect, do not write, record, leave dirty, surface for review.** Recorded as D-10.

| Option | Behaviour | Why not |
|---|---|---|
| **Detect and flag** *(chosen)* | Preserve both sides, make the divergence visible | The local edit is delayed, indefinitely if nobody works the queue |
| Field-level merge | Apply our changed fields onto the remote payload | Needs a record of which fields we changed, which `LocalRecord` does not have; and two sides changing the same field is resolved silently either way |
| Newest timestamp wins | The later `updated_at` wins | Depends on two clocks agreeing — precisely the trap I-7 describes — and still discards one side silently |

The justification is an asymmetry, and it is the same one as `DESIGN.md` §1. Not pushing our
edit is **recoverable**: it is still local, still flagged, still visible. Overwriting theirs is
**unrecoverable**: gone from both systems, and nobody knows it existed. Two failure modes with
very different costs should not be decided by whichever process ran last.

## 6. What breaks at scale

500 tenants, every 5 minutes — 100 sync cycles a minute.

**First to break: `_drain_timestamp_group` on a bulk import.** The I-1 fix assumes a timestamp
group fits in a modest page. A tenant importing 40k items at 2am stamps thousands of records
inside one second; the drain path doubles its limit until it can see past that second, pulling
the whole group into memory in one call. This is `SCALE.md`'s 2am bulk-edit scenario arriving
through a different door. Mitigation: cap the drain and fall back to overlap-and-deduplicate,
trading bounded re-delivery for a bounded page.

**Second: the conflict queue is unbounded and has no owner.** The §5 policy converts silent
corruption into a queue, which is the right trade only if somebody drains it. At 500 tenants an
unattended queue means local edits stop reaching the ERP — quietly, because nothing errors.

**Third: crash-safety is now at-least-once, deliberately.** I-4 chose re-delivery over loss.
That is sound only while `_apply` stays idempotent on `external_id` and `idem_key` is durable
before the first attempt — properties a future change can break without any test failing unless
they are asserted. They are, in `tests/sync/`.

**How we would know before a customer tells us.** The fixes deliberately convert loud corruption
into quiet non-convergence, so the monitoring has to change with them. Error rate is now the
wrong signal; **age** is the right one:

| Signal | Alert when | Catches |
|---|---|---|
| `dirty_record_age` p95 | older than ~3 cycles | push failing silently, attempts exhausted |
| `open_conflict_age` p95 | older than one business day | the queue has no owner |
| `cursor_lag` = now − cursor | above ~2 cycles | pull stalled, or a drain loop spinning |
| `drain_group_size` max | above the page cap | a bulk import is arriving |
| `writes_per_logical_edit` | any value > 1 | I-2 has regressed |

The last one matters most. MAIA-830 was found by a customer reading their own price history.
It should have been a counter.
