#!/usr/bin/env python3
"""P3-0 — the tenant index. Built once, per tenant, before any lane runs.

Three of the confirmed traps are handled *here* rather than inside a lane, which is the
architectural claim `DESIGN.md` §2 and `DECISIONS.md` D-03 rest on:

  TR-05  non-item rows are excluded from the candidate set at build time
  TR-01  a supersession map redirects any disabled code to its active successor
  TR-06  the barcode index knows when a barcode is *not* unique

A per-lane fix would have to be written once for the alias lane, again for the barcode
lane (which has the identical exposure), and again for every lane added later. Answer
normalisation is a property of the answer, not of the lane that produced it.

Data assumptions are **asserted at build time**, not trusted. If the catalogue changes
shape the index refuses to build rather than quietly resolving to the wrong thing.
"""
from __future__ import annotations

import csv
import pathlib
from dataclasses import dataclass, field

DATA = pathlib.Path(__file__).resolve().parents[2] / "data"

CATALOGUES = {"acme": "catalogue_acme.csv", "nordic": "catalogue_nordic.csv"}
CODE_PREFIX = {"acme": "ACM-", "nordic": "NRD-"}

# TR-05. Ledger artefacts that live in the item table. Excluded by *name*, with the
# `*-MISC*` code convention used only as a cross-check - a name is what a buyer types,
# a code convention is what an ERP happens to use this year.
NON_ITEM_NAMES = {
    "delivery fee", "misc charge", "opening balance", "sample - do not sell",
}


@dataclass(frozen=True)
class Item:
    tenant: str
    item_code: str
    item_name: str
    brand: str
    item_group: str
    stock_uom: str
    barcode: str
    disabled: bool


@dataclass
class TenantIndex:
    tenant: str
    items: dict[str, Item] = field(default_factory=dict)          # every row, incl. disabled
    active_codes: set[str] = field(default_factory=set)           # sellable answers only
    superseded: dict[str, str] = field(default_factory=dict)      # disabled code -> successor
    orphan_disabled: set[str] = field(default_factory=set)        # disabled, no successor
    non_items: set[str] = field(default_factory=set)
    by_barcode: dict[str, list[str]] = field(default_factory=dict)

    # ---------------------------------------------------------------- TR-01
    def resolve(self, code: str) -> tuple[str | None, str]:
        """Normalise a code any lane produced into something safe to return.

        Returns `(code_or_None, note)`. This is the single choke point every candidate
        passes through, so a lane cannot answer with a superseded, non-item, or unknown
        code even by accident.
        """
        if code in self.non_items:
            return None, "not_an_item"
        if code in self.active_codes:
            return code, "active"
        if code in self.superseded:
            return self.superseded[code], "superseded_redirect"
        if code in self.orphan_disabled:
            # Disabled with nothing to redirect to. Answering would ship a dead item;
            # the buyer needs to be told, not silently given something else.
            return None, "superseded_no_successor"
        return None, "unknown_code"


def _norm_name(name: str) -> str:
    return " ".join(name.split()).strip().lower()


def build_tenant_index(tenant: str) -> TenantIndex:
    idx = TenantIndex(tenant=tenant)
    by_name_active: dict[str, list[str]] = {}
    disabled: list[Item] = []

    with open(DATA / CATALOGUES[tenant], encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            item = Item(tenant=tenant, item_code=row["item_code"],
                        item_name=row["item_name"], brand=row["brand"],
                        item_group=row["item_group"], stock_uom=row["stock_uom"],
                        barcode=row["barcode"].strip(), disabled=row["disabled"] == "1")
            idx.items[item.item_code] = item

            if _norm_name(item.item_name) in NON_ITEM_NAMES:      # TR-05
                idx.non_items.add(item.item_code)
                continue
            if item.disabled:
                disabled.append(item)
                continue
            idx.active_codes.add(item.item_code)
            by_name_active.setdefault(_norm_name(item.item_name), []).append(item.item_code)

    # TR-01. A disabled item redirects only to an unambiguous active same-name successor.
    for item in disabled:
        successors = by_name_active.get(_norm_name(item.item_name), [])
        if len(successors) == 1:
            idx.superseded[item.item_code] = successors[0]
        else:
            idx.orphan_disabled.add(item.item_code)

    # TR-06. A barcode is decisive only when it maps to exactly one active, sellable item.
    for code in idx.active_codes:
        bc = idx.items[code].barcode
        if bc:
            idx.by_barcode.setdefault(bc, []).append(code)
    for codes in idx.by_barcode.values():
        codes.sort()                                              # determinism

    _assert_shape(idx)
    return idx


def _assert_shape(idx: TenantIndex) -> None:
    """Data assumptions, checked rather than trusted.

    Each of these was verified once by a probe; asserting them here means a catalogue
    that stops satisfying them fails loudly at build time instead of resolving to the
    wrong item at 20x cost.
    """
    prefix = CODE_PREFIX[idx.tenant]
    leaked = [c for c in idx.active_codes if not c.startswith(prefix)]
    assert not leaked, f"{idx.tenant}: codes outside its own namespace: {leaked[:5]}"

    by_code = {c for c in idx.items if "MISC" in c}
    assert idx.non_items == by_code, (
        f"{idx.tenant}: the non-item name list and the *-MISC* code convention disagree "
        f"(names-only {idx.non_items - by_code}, codes-only {by_code - idx.non_items}). "
        "One of the two assumptions has moved; do not guess which.")

    assert not idx.orphan_disabled, (
        f"{idx.tenant}: {len(idx.orphan_disabled)} disabled item(s) have no unambiguous "
        f"active successor, e.g. {sorted(idx.orphan_disabled)[:3]}. Handled safely by "
        "abstaining, but it means TR-01's 38/38 coverage no longer holds.")


@dataclass(frozen=True)
class AliasRow:
    tenant: str
    customer_id: str
    customer_sku: str
    item_code: str
    valid_from: str
    valid_to: str
    source: str
    confidence: float


@dataclass
class AliasIndex:
    """Buyer-SKU aliases, keyed on (tenant, customer, sku).

    `confidence` is loaded and carried as evidence but is **never** used to gate
    (TR-02 / D-04): on train, precision at `confidence=1.0` is 22.6% and at 0.55 it is
    100%. The column is anti-informative here, so treating it as a prior is worse than
    ignoring it.
    """
    rows: dict[tuple[str, str, str], list[AliasRow]] = field(default_factory=dict)

    def lookup(self, tenant: str, customer_id: str, sku: str, order_date: str
               ) -> tuple[list[AliasRow], list[AliasRow]]:
        """Return `(valid, expired)` rows for this key as of `order_date`. TR-08."""
        all_rows = self.rows.get((tenant, customer_id, sku.strip().lower()), [])
        valid, expired = [], []
        for r in all_rows:
            # Inclusive on both ends: a mapping is valid *through* its valid_to date.
            if r.valid_from and order_date < r.valid_from:
                expired.append(r)
            elif r.valid_to and order_date > r.valid_to:
                expired.append(r)
            else:
                valid.append(r)
        return valid, expired


def build_alias_index() -> AliasIndex:
    idx = AliasIndex()
    with open(DATA / "customer_sku_map.csv", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            r = AliasRow(tenant=row["tenant"], customer_id=row["customer_id"],
                         customer_sku=row["customer_sku"].strip(),
                         item_code=row["item_code"], valid_from=row["valid_from"],
                         valid_to=row["valid_to"], source=row["source"],
                         confidence=float(row["confidence"]))
            idx.rows.setdefault((r.tenant, r.customer_id, r.customer_sku.lower()), []).append(r)
    for rows in idx.rows.values():
        rows.sort(key=lambda r: (r.item_code, r.valid_from))       # determinism
    return idx


def _main() -> None:
    print("=== P3-0 index build ===")
    alias = build_alias_index()
    print(f"  alias keys: {len(alias.rows)}")
    for tenant in CATALOGUES:
        idx = build_tenant_index(tenant)
        dupes = sum(1 for v in idx.by_barcode.values() if len(v) > 1)
        print(f"\n  {tenant}")
        print(f"    rows in catalogue     {len(idx.items)}")
        print(f"    non-items excluded    {len(idx.non_items)}  (TR-05)")
        print(f"    active, sellable      {len(idx.active_codes)}")
        print(f"    superseded -> active  {len(idx.superseded)}  (TR-01)")
        print(f"    disabled, no successor{len(idx.orphan_disabled):>3}")
        print(f"    barcodes indexed      {len(idx.by_barcode)}, of which "
              f"{dupes} map to >1 active item  (TR-06)")


if __name__ == "__main__":
    _main()
