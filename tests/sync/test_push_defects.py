"""Task 5 — defects on the push path. One test per defect, each named for its mechanism."""
from __future__ import annotations

import pytest

from fake_erp import ErpTimeout
from sync_adapter import pull, push


# ---------------------------------------------------------------- D2 (MAIA-830)
def test_d2_retry_after_a_504_writes_twice(erp_factory, store):
    """INVARIANT: one logical local edit produces at most one remote write.

    The ERP commits and *then* raises the 504, so a retry is a second write of an edit
    that already landed. Its Idempotency-Key would suppress that, except the adapter
    hashes `attempt` into the key — so the retry can never present the same key, and the
    exact-string match never fires. `time.time()` is in the hash too, which breaks the
    key non-deterministically; on Windows the 15.625 ms clock resolution hides that term,
    on Linux it would not. Two defects in one four-line function.

    `timeout_rate=1.0` makes the 504 certain, removing the RNG from the test.
    """
    erp = erp_factory(timeout_rate=1.0, n=5)
    pull(erp, store, page_size=50)

    eid = sorted(erp.records)[0]
    store.records[eid].payload = dict(store.records[eid].payload, price=999.0)
    store.records[eid].dirty = True

    try:
        push(erp, store)
    except ErpTimeout:
        # Retrying with a fresh key bumps the version, so attempt 2 gets a 409 whose
        # handler then 504s and escapes. That escape is a *separate* defect and belongs
        # to D6; swallowing it here keeps this test failing for its own reason only.
        pass

    writes = [w for w in erp.write_log if w[0] == eid and w[2].get("price") == 999.0]
    assert len(writes) == 1, (
        f"one local edit produced {len(writes)} remote writes; the price history shows "
        "duplicate updates a second apart, which is MAIA-830"
    )


# ---------------------------------------------------------------- D3 (MAIA-844)
def test_d3_conflict_handler_overwrites_the_remote_edit(erp_factory, store):
    """INVARIANT: a remote edit made after our local edit is never silently discarded.

    On `ErpConflict` the adapter refetches the record to learn its *version*, then writes
    our payload with that version as the base. It never looks at the remote *payload*, so
    the 409 — the ERP telling us someone else changed this row — is converted into
    permission to overwrite them. Unconditional last-write-wins, with the winner decided
    by whoever synced last.
    """
    erp = erp_factory(timeout_rate=0.0, n=60)
    pull(erp, store, page_size=50)

    eid = "EXT-0011"
    store.records[eid].payload = dict(store.records[eid].payload, price=999.0)
    store.records[eid].dirty = True

    erp.tick(120)  # a user edits the same row in the ERP, changing uom
    erp.write(eid, {"name": "item 11", "price": 55.5, "uom": "Box"},
              base_version=erp.records[eid].version)

    push(erp, store)

    assert erp.records[eid].payload.get("uom") == "Box", (
        f"the remote edit was clobbered: payload is {erp.records[eid].payload}. "
        "uom=Box was set in the ERP after our local edit and must survive the push."
    )


# ---------------------------------------------------------------- D6 (latent)
def test_d6_a_504_inside_the_conflict_handler_aborts_the_whole_sync(erp_factory, store):
    """INVARIANT: one record's transient failure never abandons the other records.

    The retry loop guards the first `erp.write` with `except ErpTimeout`. The second
    write — the one inside the `except ErpConflict` branch — is guarded by nothing. A
    504 there escapes `push` entirely, so every dirty record after this one in the
    iteration order is silently skipped for this cycle.

    Latent because it needs a 409 and a 504 on the same record in the same attempt. At a
    15 % timeout rate and a 5-minute cadence across 500 tenants that is a daily event; it
    presents as "sync just stops sometimes", which is why it has no ticket of its own.
    """
    erp = erp_factory(timeout_rate=1.0, n=5)
    pull(erp, store, page_size=50)

    eid = sorted(erp.records)[0]
    store.records[eid].payload = dict(store.records[eid].payload, price=999.0)
    store.records[eid].dirty = True
    store.records[eid].remote_version = 0  # stale, so the first write raises ErpConflict

    try:
        push(erp, store)
    except ErpTimeout as exc:  # pragma: no cover - this is the defect
        pytest.fail(
            f"ErpTimeout escaped push(): {exc}. The write inside the ErpConflict "
            "handler is unguarded, so every later dirty record is abandoned."
        )
