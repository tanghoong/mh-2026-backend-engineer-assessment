import csv, collections, re, json
D="data/"
def rd(f):
    with open(D+f, newline='', encoding='utf-8') as fh: return list(csv.DictReader(fh))
cat={"acme":rd("catalogue_acme.csv"),"nordic":rd("catalogue_nordic.csv")}
smap=rd("customer_sku_map.csv"); train=rd("order_lines_train.csv"); hold=rd("order_lines_holdout.csv")

print("== source x confidence crosstab ==")
ct=collections.Counter((r["source"],r["confidence"]) for r in smap)
for k,v in sorted(ct.items()): print("  ",k,v)

print("\n== what actually separates twins? sample group ==")
rows=[r for r in cat["nordic"] if r["item_code"] in ("NRD-FULL0120","NRD-FULL0348","NRD-FULL0010")]
for r in rows: print("  ",r["item_code"],"|",r["item_name"],"|uom=",r["stock_uom"],"|conv=",r["uom_conversions"],"|desc=",r["description"][:70])

print("\n== -OLD items: does an active successor with same name exist? ==")
for t,rowsx in cat.items():
    byname=collections.defaultdict(list)
    for r in rowsx: byname[re.sub(r'\s*\(superseded\)','',r["item_name"]).strip().lower()].append((r["item_code"],r["disabled"]))
    olds=[r for r in rowsx if r["item_code"].endswith("-OLD")]
    hit=sum(1 for r in olds if any(d=="0" for c,d in byname[re.sub(r'\s*\(superseded\)','',r["item_name"]).strip().lower()]))
    print(f"  {t}: {len(olds)} -OLD items, {hit} have an ACTIVE same-name successor")
    for r in olds[:3]:
        k=re.sub(r'\s*\(superseded\)','',r["item_name"]).strip().lower()
        print("    ",r["item_code"],"->",byname[k])

print("\n== train lines: how many carry buyer_sku / how many of those hit the alias map ==")
idx=collections.defaultdict(list)
for r in smap: idx[(r["tenant"],r["customer_id"],r["customer_sku"].strip().lower())].append(r)
for name,rowsx in (("train",train),("holdout",hold)):
    hasbs=[r for r in rowsx if r.get("buyer_sku","").strip()]
    hit=[r for r in hasbs if (r["tenant"],r["customer_id"],r["buyer_sku"].strip().lower()) in idx]
    print(f"  {name}: buyer_sku present={len(hasbs)}/{len(rowsx)}, alias-map hit={len(hit)}")
    if name=="train":
        ok=wr=0; amb=0; expired=0
        for r in hit:
            cands=idx[(r["tenant"],r["customer_id"],r["buyer_sku"].strip().lower())]
            codes={c["item_code"] for c in cands}
            if len(codes)>1: amb+=1
            if any(c["valid_to"].strip() for c in cands): expired+=1
            gt=r["gt_item_code"].strip()
            if gt and gt in codes: ok+=1
            elif gt: wr+=1
        print(f"    of alias hits: gt-in-alias={ok} gt-NOT-in-alias={wr} ambiguous={amb} has-expired-row={expired}")

print("\n== channel / noise distribution ==")
print("  train channel:", dict(collections.Counter(r["channel"] for r in train)))
print("  hold  channel:", dict(collections.Counter(r["channel"] for r in hold)))
print("  train notes non-empty:", sum(1 for r in train if r.get("notes","").strip()))
ex=[r for r in train if r.get("notes","").strip()][:5]
for r in ex: print("    note:",repr(r["notes"])[:70],"| gt=",r["gt_item_code"])

print("\n== blank-gt lines: what do they look like? ==")
bl=[r for r in train if not r["gt_item_code"].strip()]
for r in bl[:12]: print("   ",r["line_id"],r["tenant"],repr(r["raw_text"])[:65])
