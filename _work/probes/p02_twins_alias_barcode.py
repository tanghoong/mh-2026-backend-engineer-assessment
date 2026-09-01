import csv, collections, re
D="data/"
def rd(f):
    with open(D+f, newline='', encoding='utf-8') as fh: return list(csv.DictReader(fh))
cat={"acme":rd("catalogue_acme.csv"),"nordic":rd("catalogue_nordic.csv")}
smap=rd("customer_sku_map.csv"); train=rd("order_lines_train.csv"); hold=rd("order_lines_holdout.csv")
allcodes={t:{r["item_code"] for r in rows} for t,rows in cat.items()}

print("== T5b: 'twins' = same brand+item_group+core name, differing ONLY by pack/size, both active ==")
for t,rows in cat.items():
    key=collections.defaultdict(list)
    for r in rows:
        if r["disabled"]=="1" or "MISC" in r["item_code"]: continue
        # strip trailing pack/size tokens to get a core name
        core=re.sub(r'\s*\b(\d+(\.\d+)?\s*(kg|g|l|ml|mm|pcs|pc|nos|box|ctn|carton|pkt|tin))\b','',r["item_name"],flags=re.I).strip().lower()
        key[(r["brand"],r["item_group"],core)].append((r["item_code"],r["item_name"],r["stock_uom"]))
    tw={k:v for k,v in key.items() if len(v)>1}
    print(f" {t}: {len(tw)} twin-groups, {sum(len(v) for v in tw.values())} codes")
    for k,v in list(tw.items())[:4]: print("    ",k[2][:45],"->",[x[0]+"/"+x[2] for x in v])

print("\n== T6: customer_sku_map defects ==")
print(" rows:", len(smap), "| cols:", list(smap[0].keys()))
print(" source counts:", collections.Counter(r["source"] for r in smap))
conf=collections.Counter(r["confidence"] for r in smap)
print(" confidence dist:", dict(sorted(conf.items())))
exp=[r for r in smap if r["valid_to"].strip()]
print(f" expired (valid_to set): {len(exp)} e.g.", [(r['customer_sku'],r['item_code'],r['valid_to']) for r in exp[:4]])
dup=collections.defaultdict(set)
for r in smap: dup[(r["tenant"],r["customer_id"],r["customer_sku"].strip().lower())].add(r["item_code"])
amb={k:v for k,v in dup.items() if len(v)>1}
print(f" SAME (tenant,customer,sku) -> multiple item_code: {len(amb)}")
for k,v in list(amb.items())[:6]: print("    ",k,"->",sorted(v))
xt=[r for r in smap if r["item_code"] not in allcodes.get(r["tenant"],set())]
print(f" alias item_code NOT in own tenant catalogue: {len(xt)}", [(r['tenant'],r['customer_sku'],r['item_code']) for r in xt[:6]])
other={"acme":allcodes["nordic"],"nordic":allcodes["acme"]}
xs=[r for r in smap if r["customer_sku"].strip() in other[r["tenant"]]]
print(f" buyer SKU that IS another tenant's item_code: {len(xs)}", [(r['tenant'],r['customer_sku'],r['item_code']) for r in xs[:6]])

print("\n== T7: order-line buyer_sku / barcode looking cross-tenant ==")
for name,rows in (("train",train),("holdout",hold)):
    bs=[r for r in rows if r.get("buyer_sku","").strip() and r["buyer_sku"].strip() in other[r["tenant"]]]
    rawc=[r for r in rows if r.get("raw_text","").strip() and any(w in other[r["tenant"]] for w in r["raw_text"].split())]
    print(f" {name}: buyer_sku==other-tenant-code {len(bs)} | raw_text contains other-tenant-code {len(rawc)}")
    for r in (bs+rawc)[:4]: print("    ",r["line_id"],r["tenant"],repr(r["raw_text"])[:60],"buyer_sku=",r.get("buyer_sku"))

print("\n== T8: barcode coverage & collisions ==")
for t,rows in cat.items():
    bc=[r["barcode"] for r in rows if r["barcode"].strip()]
    print(f" {t}: {len(bc)}/{len(rows)} items have barcode; distinct={len(set(bc))}; collisions={len(bc)-len(set(bc))}")
allbc=collections.defaultdict(set)
for t,rows in cat.items():
    for r in rows:
        if r["barcode"].strip(): allbc[r["barcode"]].add(t)
print(" barcodes present in BOTH tenants:", sum(1 for v in allbc.values() if len(v)>1))
for name,rows in (("train",train),("holdout",hold)):
    n=sum(1 for r in rows if r.get("raw_barcode","").strip())
    print(f" {name}: lines with raw_barcode = {n}")
