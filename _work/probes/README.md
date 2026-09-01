# Evidence probes

Read-only. Run from the repo root:

    python3 _work/probes/p04_alias_precision.py     # locally: py -3 ...

| Script | Establishes |
|---|---|
| `p01_labels_catalogue.py` | TR-03 abstain rate; TR-05 non-item rows; labels vs disabled/-OLD |
| `p02_twins_alias_barcode.py` | TR-04 twin groups; TR-06 barcode collisions; TR-07/08 alias defects; TR-09 refutation |
| `p03_alias_hits_abstain.py` | supersession successors; alias hit rate; abstain sub-populations |
| `p04_alias_precision.py` | **TR-01 / TR-02** — alias precision by source and confidence |

None of these write anything. `data/` is read-only.
