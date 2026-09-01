#!/usr/bin/env python3
"""Two-way sync between our local item store and the ERP in fake_erp.py.

Repaired for Task 5. Each change is annotated with the invariant it restores; the
invariants themselves, and the reasoning behind their exact wording, are in SYNC.md §2.

  I-1  the cursor never advances past a timestamp group that has not been fully drained
  I-2  one logical local edit produces at most one remote write
  I-3  no write is based on remote state we have not read
  I-4  the cursor is durable only after the work it covers is durable
  I-5  pull never clears `dirty` on a record it did not push
  I-6  a transient failure on one record never affects another
  I-7  a timestamp's zone is part of its type

Original tickets: MAIA-812 (I-1), MAIA-830 (I-2), MAIA-844 (I-3).
`fake_erp.py` is the vendor's system and is unmodified.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from fake_erp import ErpConflict, ErpTimeout, FakeErp, Record

# fake_erp stamps updated_at in the server's local zone and returns it without an
# offset. The offset is part of the vendor contract, not something we can discover
# at runtime, so it is named here rather than inferred. (I-7)
SERVER_UTC_OFFSET_HOURS = 8
_TS_FMT = "%Y-%m-%d %H:%M:%S"


def server_local_to_utc(ts: str) -> str:
    """Convert an ERP timestamp (+08:00, rendered bare) to UTC. (I-7)"""
    return (datetime.strptime(ts, _TS_FMT)
            - timedelta(hours=SERVER_UTC_OFFSET_HOURS)).strftime(_TS_FMT)


@dataclass
class LocalRecord:
    external_id: str
    payload: dict
    remote_version: int
    updated_at_utc: str          # UTC only. Never holds a server-local value. (I-7)
    dirty: bool = False

    # I-7: the raw server-local string, kept because the pagination cursor lives in
    # the ERP's zone and must never be compared against updated_at_utc.
    remote_updated_at_server: str = ""

    # I-2: the Idempotency-Key for the current dirty episode. Assigned before the
    # first attempt and reused by every retry; cleared once the push lands. In a real
    # store this column is persisted, so a process killed mid-retry presents the same
    # key on restart. A key regenerated after a crash is a new key and the guarantee
    # is gone.
    idem_key: str | None = None

    # I-2: bumped by whatever marks the record dirty, so that edit -> push -> revert
    # -> push is two logical edits rather than one repeated key. Nothing in this
    # harness edits through a helper, so it stays 0 here; see SYNC.md §3.
    local_revision: int = 0


@dataclass
class Conflict:
    """A divergence we refused to resolve on our own. (I-3, I-5)"""
    external_id: str
    reason: str
    local_payload: dict
    remote_payload: dict
    local_version: int
    remote_version: int
    detected_at_utc: str


@dataclass
class LocalStore:
    """Stands in for our Postgres tables. Committed writes only."""
    records: dict = field(default_factory=dict)
    applied_log: list = field(default_factory=list)

    # I-7: named for its zone. This is server-local because `list_changes` compares
    # it as a string against server-stamped values. Converting it to UTC would be a
    # correct-looking change that breaks pagination silently.
    cursor_server_local: str | None = None

    conflicts: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)

    @property
    def cursor(self) -> str | None:
        return self.cursor_server_local

    def upsert(self, rec: LocalRecord) -> None:
        self.records[rec.external_id] = rec
        self.applied_log.append((rec.external_id, rec.remote_version))

    def set_cursor(self, cursor: str) -> None:
        self.cursor_server_local = cursor

    def record_conflict(self, local: LocalRecord, remote: Record, reason: str) -> None:
        self.conflicts[local.external_id] = Conflict(
            external_id=local.external_id,
            reason=reason,
            local_payload=dict(local.payload),
            remote_payload=dict(remote.payload),
            local_version=local.remote_version,
            remote_version=remote.version,
            detected_at_utc=now_utc(),
        )

    def record_error(self, external_id: str, exc: BaseException) -> None:
        self.errors.append((external_id, type(exc).__name__, str(exc)))


def now_utc() -> str:
    return time.strftime(_TS_FMT, time.gmtime())


def idempotency_key(external_id: str, payload: dict, local_revision: int = 0) -> str:
    """Stable across retries, by construction. (I-2)

    The previous version hashed the retry counter and `time.time()`, so no two
    attempts could ever present the same key and the ERP's exact-match window could
    never fire. Both are gone: the key is a pure function of the local change
    identity, which is what the vendor's idempotency contract is keyed on.
    """
    blob = json.dumps({"id": external_id, "payload": payload, "rev": local_revision},
                      sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


# --------------------------------------------------------------------- pull

def _drain_timestamp_group(erp: FakeErp, since: str | None, ts: str, page_size: int) -> list:
    """Fetch a whole timestamp group that is wider than one page. (I-1)

    Trimming the trailing partial second is what makes I-1 hold, but it cannot make
    progress when a single timestamp holds more records than `page_size` - the trimmed
    batch is empty and the cursor never moves. This is the failure the naive version of
    the I-1 fix introduces, so it is handled rather than left to loop forever.
    """
    limit = page_size * 2
    while True:
        page = erp.list_changes(since=since, limit=limit)
        rows = [r for r in page if r.updated_at <= ts]
        if len(rows) < len(page) or len(page) < limit:
            return rows          # we can see past `ts`, so the group is complete
        limit *= 2


def _apply(store: LocalStore, rec: Record) -> bool:
    """Write one remote record locally. Returns True if it was applied."""
    local = store.records.get(rec.external_id)
    if local is not None and local.dirty:
        # I-5: never clear `dirty` on a record we did not push. Stated as a rule about
        # the flag, not about which side is newer: the old "newer wins" guard failed
        # open, and phrasing it as a timestamp comparison would also make this fix
        # depend on I-7, collapsing two defects into one repair.
        store.record_conflict(local, rec, reason="remote_changed_while_local_edit_pending")
        return False
    store.upsert(LocalRecord(
        external_id=rec.external_id,
        payload=dict(rec.payload),
        remote_version=rec.version,
        updated_at_utc=server_local_to_utc(rec.updated_at),   # I-7
        remote_updated_at_server=rec.updated_at,
        dirty=False,
    ))
    return True


def pull(erp: FakeErp, store: LocalStore, page_size: int = 50) -> int:
    """Pull remote changes since the stored cursor into the local store."""
    pulled = 0
    while True:
        page = erp.list_changes(since=store.cursor_server_local, limit=page_size)
        if not page:
            break

        last_page = len(page) < page_size
        if last_page:
            batch = page                    # nothing is truncated: safe to take all
        else:
            # I-1: `list_changes` paginates on a second-resolution timestamp and filters
            # with a strict `>`, so the trailing timestamp group may be cut in half by
            # the page limit. Consuming it and storing its timestamp as the cursor is
            # what makes MAIA-812 permanent rather than merely late.
            boundary = page[-1].updated_at
            batch = [r for r in page if r.updated_at < boundary]
            if not batch:
                batch = _drain_timestamp_group(
                    erp, store.cursor_server_local, boundary, page_size)

        for rec in batch:
            if _apply(store, rec):
                pulled += 1

        # I-4: the cursor becomes durable only after the work it covers is durable.
        # A crash before this line causes re-delivery, which is harmless because
        # `_apply` is idempotent on external_id - that idempotence is a precondition
        # of this ordering, not an incidental property. The system is deliberately
        # at-least-once; at-most-once is what the old ordering bought, and it paid
        # for it with the records it dropped.
        if batch:
            store.set_cursor(batch[-1].updated_at)

        if last_page:
            break
    return pulled


# --------------------------------------------------------------------- push

def _commit_push(store: LocalStore, rec: LocalRecord, remote: Record) -> None:
    rec.remote_version = remote.version
    rec.updated_at_utc = server_local_to_utc(remote.updated_at)   # I-7
    rec.remote_updated_at_server = remote.updated_at
    rec.dirty = False
    rec.idem_key = None            # I-2: the dirty episode is over
    store.upsert(rec)


def _push_one(erp: FakeErp, store: LocalStore, rec: LocalRecord, max_attempts: int) -> bool:
    """Push one record. Never raises. (I-6)"""
    if rec.idem_key is None:
        # I-2: minted once, before the first attempt, and reused by every retry.
        rec.idem_key = idempotency_key(rec.external_id, rec.payload, rec.local_revision)

    for _ in range(max_attempts):
        try:
            remote = erp.write(rec.external_id, rec.payload,
                               base_version=rec.remote_version,
                               idempotency_key=rec.idem_key)
        except ErpTimeout:
            # The 504 arrives *after* the commit, so we cannot tell from the exception
            # whether the write landed. Retrying with the same key is what makes that
            # ambiguity safe: the ERP replays its stored response instead of writing
            # again. (I-2)
            continue
        except ErpConflict:
            # I-3: a 409 is the ERP saying someone else changed this row. The old code
            # refetched the *version* and rewrote our payload with it, turning the
            # warning into permission to overwrite. We read the remote payload, record
            # the divergence, and write nothing.
            #
            # Policy: detect, do not overwrite, leave dirty, surface for review. Not
            # pushing our edit is recoverable - it is still here and still flagged.
            # Overwriting theirs is not. See SYNC.md §2 I-3 and DECISIONS.md D-10.
            current = erp.get(rec.external_id)
            if current is not None:
                store.record_conflict(rec, current, reason="remote_version_ahead")
            return False
        except Exception as exc:                                  # pragma: no cover
            store.record_error(rec.external_id, exc)              # I-6
            return False
        _commit_push(store, rec, remote)
        return True

    # I-6: attempts exhausted. Stay dirty, surface the failure, let the next record run.
    store.record_error(rec.external_id,
                       ErpTimeout(f"{rec.external_id}: {max_attempts} attempts, all 504"))
    return False


def push(erp: FakeErp, store: LocalStore, max_attempts: int = 3) -> int:
    """Push locally-dirty records to the ERP."""
    pushed = 0
    for rec in list(store.records.values()):
        if not rec.dirty:
            continue
        # I-6: one record's outcome never reaches another. The old loop guarded the
        # first write and left the retry inside the conflict handler unguarded, so a
        # 504 there escaped push() and abandoned every later dirty record.
        if _push_one(erp, store, rec, max_attempts):
            pushed += 1
    return pushed


def sync(erp: FakeErp, store: LocalStore) -> dict:
    return {"pulled": pull(erp, store), "pushed": push(erp, store),
            "conflicts": len(store.conflicts), "errors": len(store.errors)}
