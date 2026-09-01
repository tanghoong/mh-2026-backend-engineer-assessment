"""Test fixtures for Task 5.

`starter/sync/` is not a package, so it is put on the path here rather than
restructured — the brief treats those files as production code under repair,
not as something to reorganise.
"""
from __future__ import annotations

import sys
from pathlib import Path

SYNC_DIR = Path(__file__).resolve().parents[2] / "starter" / "sync"
if str(SYNC_DIR) not in sys.path:
    sys.path.insert(0, str(SYNC_DIR))

import pytest  # noqa: E402

from fake_erp import FakeErp  # noqa: E402
from sync_adapter import LocalRecord, LocalStore  # noqa: E402


@pytest.fixture
def erp_factory():
    """Build a FakeErp with an explicit timeout rate.

    `timeout_rate=0.0` makes writes always succeed; `1.0` makes every write
    commit and *then* raise a 504, which is the vendor behaviour the adapter
    has to survive. Both remove the RNG from the test.
    """

    def _make(seed: int = 11, timeout_rate: float = 0.0, n: int = 60) -> FakeErp:
        erp = FakeErp(seed=seed, timeout_rate=timeout_rate)
        erp.seed_records(n)
        return erp

    return _make


@pytest.fixture
def store() -> LocalStore:
    return LocalStore()


@pytest.fixture
def local_record():
    def _make(external_id: str, payload: dict, remote_version: int,
              updated_at: str, dirty: bool = True) -> LocalRecord:
        return LocalRecord(external_id=external_id, payload=dict(payload),
                           remote_version=remote_version,
                           updated_at_utc=updated_at, dirty=dirty)

    return _make
