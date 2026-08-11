#!/usr/bin/env python3
"""A deliberately unhelpful ERP, standing in for the real third-party system.

You do not need to change this file to complete Task 5, and you should not:
treat it as a vendor system you cannot patch. Read it carefully - its exact
semantics (including the annoying ones) are the environment your adapter has
to survive.

Semantics worth noticing:
  * list_changes() paginates by updated_at with SECOND resolution, and many
    records share a timestamp.
  * write() is not transactional across records in a batch.
  * The server sometimes returns a 504 AFTER committing the write.
  * Idempotency-Key is honoured for 60 seconds, exact string match only.
  * updated_at is stamped by the server, in the server's local zone (+08:00),
    and returned without an offset.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


class ErpTimeout(Exception):
    """504 from the ERP. Says nothing about whether the write landed."""


class ErpConflict(Exception):
    """409: the record changed underneath you."""


@dataclass
class Record:
    external_id: str
    payload: dict
    version: int
    updated_at: str          # "YYYY-MM-DD HH:MM:SS", server local time (+08:00)


@dataclass
class FakeErp:
    seed: int = 7
    timeout_rate: float = 0.15
    clock: int = 0
    records: dict = field(default_factory=dict)
    _idem: dict = field(default_factory=dict)
    _rng: random.Random = field(default=None)
    write_log: list = field(default_factory=list)

    def __post_init__(self):
        self._rng = random.Random(self.seed)

    # -- clock -----------------------------------------------------------
    def _now(self) -> str:
        # server local time (+08:00), rendered without an offset
        h, m, s = (self.clock // 3600) % 24, (self.clock // 60) % 60, self.clock % 60
        return f"2026-08-0{1 + self.clock // 86400} {h:02d}:{m:02d}:{s:02d}"

    def tick(self, seconds: int = 1) -> None:
        self.clock += seconds

    # -- read ------------------------------------------------------------
    def list_changes(self, since: str | None, limit: int = 50) -> list[Record]:
        """Records with updated_at > `since`, oldest first, capped at `limit`.

        `since` is compared as a string, at second resolution. Ties are common.
        """
        rows = sorted(self.records.values(), key=lambda r: (r.updated_at, r.external_id))
        if since:
            rows = [r for r in rows if r.updated_at > since]
        return rows[:limit]

    def get(self, external_id: str) -> Record | None:
        return self.records.get(external_id)

    # -- write -----------------------------------------------------------
    def write(self, external_id: str, payload: dict, base_version: int | None,
              idempotency_key: str | None = None) -> Record:
        if idempotency_key and idempotency_key in self._idem:
            return self._idem[idempotency_key]

        existing = self.records.get(external_id)
        if existing and base_version is not None and existing.version != base_version:
            raise ErpConflict(f"{external_id}: have v{existing.version}, you sent v{base_version}")

        rec = Record(external_id=external_id, payload=dict(payload),
                     version=(existing.version + 1 if existing else 1),
                     updated_at=self._now())
        self.records[external_id] = rec
        self.write_log.append((external_id, rec.version, dict(payload)))
        if idempotency_key:
            self._idem[idempotency_key] = rec

        # committed - and now the connection dies on the way back
        if self._rng.random() < self.timeout_rate:
            raise ErpTimeout(f"504 after commit of {external_id} v{rec.version}")
        return rec

    # -- test seam -------------------------------------------------------
    def seed_records(self, n: int = 40) -> None:
        for i in range(n):
            self.tick(self._rng.choice([0, 0, 0, 1, 1, 5]))
            eid = f"EXT-{i:04d}"
            self.records[eid] = Record(eid, {"name": f"item {i}", "price": 10.0 + i, "uom": "Nos"},
                                       1, self._now())
