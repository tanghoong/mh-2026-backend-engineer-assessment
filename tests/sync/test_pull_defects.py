"""Task 5 — defects on the pull path. One test per defect, each named for its mechanism.

Each test states the invariant it restores. A test that would pass because a
*different* defect was fixed is a broken test, not a lucky one.
"""
from __future__ import annotations

import pytest

from sync_adapter import pull


# ---------------------------------------------------------------- D1 (MAIA-812)
def test_d1_cursor_tie_at_page_boundary_drops_records(erp_factory, store):
    """INVARIANT: every record the ERP has ends up locally, whatever the page size.

    `list_changes` paginates on `updated_at` at SECOND resolution and filters with a
    strict `>`. The adapter stores `page[-1].updated_at` as its cursor, so any record
    sharing that second with the last row of the page is skipped permanently — not
    late, never. The seeded batch has 16 timestamps shared by more than one record.
    """
    erp = erp_factory(n=60)
    pull(erp, store, page_size=50)

    missing = set(erp.records) - set(store.records)
    assert not missing, (
        f"{len(missing)} record(s) never pulled: {sorted(missing)}. "
        "A record tied on updated_at with the last row of a page is lost forever."
    )


# ---------------------------------------------------------------- D4 (latent)
def test_d4_cursor_advances_before_the_page_is_applied(erp_factory, store):
    """INVARIANT: the cursor never moves ahead of work that has been committed.

    `pull` calls `set_cursor(page[-1].updated_at)` *before* applying the page. The brief
    says the process can be killed at any moment; if it dies mid-page the cursor has
    already advanced past records that were never written, and they are gone.

    No ticket yet because the process has not happened to die mid-page in production.
    It surfaces on the first deploy restart or OOM kill during a large initial sync.
    """
    erp = erp_factory(n=60)
    applied: list[str] = []
    real_upsert = store.upsert

    def crash_after_three(rec):
        if len(applied) >= 3:
            raise KeyboardInterrupt("process killed mid-page")
        applied.append(rec.external_id)
        real_upsert(rec)

    store.upsert = crash_after_three
    with pytest.raises(KeyboardInterrupt):
        pull(erp, store, page_size=50)

    if store.cursor is None:
        return  # nothing durably advanced: correct
    highest_applied = max(store.records[eid].updated_at_utc for eid in applied)
    assert store.cursor <= highest_applied, (
        f"cursor={store.cursor!r} is ahead of the last applied record "
        f"({highest_applied!r}); everything between them is lost on restart."
    )


# ---------------------------------------------------------------- D5 (latent)
def test_d5_pull_silently_discards_an_unsent_local_edit(erp_factory, store, local_record):
    """INVARIANT: an unsent local edit is never dropped without being recorded.

    The dirty-guard in `pull` only protects a local edit when its timestamp is strictly
    newer than the remote's. Otherwise it upserts over the top with `dirty=False`, so a
    pending edit vanishes with no conflict, no log line and no ticket — the operator
    simply finds their change gone.

    Latent because it needs a remote touch between a local edit and the next push. At a
    5-minute cadence across 500 tenants that window is open most of the time.
    """
    erp = erp_factory(n=5)
    pull(erp, store, page_size=50)

    eid = sorted(erp.records)[0]
    store.records[eid].payload = dict(store.records[eid].payload, price=999.0)
    store.records[eid].dirty = True

    erp.tick(120)  # the ERP moves on, so the remote row is now newer than ours
    erp.write(eid, {"name": "touched remotely", "price": 1.0, "uom": "Nos"},
              base_version=erp.records[eid].version)

    pull(erp, store, page_size=50)

    local = store.records[eid]
    assert local.dirty or local.payload.get("price") == 999.0, (
        "the unsent local edit (price=999.0) was overwritten by pull and the record "
        "was marked clean, so push will never send it and the edit is silently lost"
    )


# ---------------------------------------------------------------- D7 (latent)
def test_d7_server_local_timestamps_are_stored_in_a_field_named_utc(erp_factory, store):
    """INVARIANT: `LocalRecord.updated_at_utc` holds UTC.

    `fake_erp` stamps `updated_at` in the server's local zone (+08:00) and returns it
    with no offset. `pull` assigns that string straight into `updated_at_utc`, and
    `sync_adapter.now_utc()` produces real UTC — so the two are 8 hours apart while
    looking identical in shape. Every comparison between them is wrong by 8 hours,
    including the dirty-guard in `pull` that decides whether to keep a local edit.

    Latent because nothing in the current code path compares a `now_utc()` value against
    a stored one. The first piece of code that does inherits a silent 8-hour skew.
    """
    erp = erp_factory(n=5)
    pull(erp, store, page_size=50)

    eid = sorted(erp.records)[0]
    server_local = erp.records[eid].updated_at
    stored = store.records[eid].updated_at_utc

    assert stored != server_local, (
        f"stored updated_at_utc={stored!r} is the raw server-local (+08:00) string; "
        "the field name claims UTC and the value is 8 hours ahead of it"
    )
