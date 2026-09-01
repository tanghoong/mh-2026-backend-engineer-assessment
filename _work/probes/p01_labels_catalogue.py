import csv, collections, json, sys
D="data/"
def rd(f):
    with open(D+f, newline='', encoding='utf-8') as fh: return list(csv.DictReader(fh))

train=rd("order_lines_train.csv"); hold=rd("order_lines_holdout.csv")
acme=rd("catalogue_acme.csv"); nordic=rd("catalogue_nordic.csv")
smap=rd("customer_sku_map.csv")
cat={"acme":acme,"nordic":nordic}
allcodes={t:{r["item_code"] for r in rows} for t,rows in cat.items()}

print("== T1: blank gt_item_code (abstain rate) ==")
blank=sum(1 for r in train if not r["gt_item_code"].strip())
print(f"train n={len(train)} blank={blank} ({blank/len(train):.1%})")
per=collections.Counter((r["tenant"], "blank" if not r["gt_item_code"].strip() else "labelled") for r in train)
print(" per-tenant:", dict(per))
print(" holdout n=", len(hold), "tenants:", collections.Counter(r["tenant"] for r in hold))

print("\n== T2: gt_item_code that does NOT exist in its tenant catalogue ==")
bad=[(r["line_id"],r["tenant"],r["gt_item_code"]) for r in train
     if r["gt_item_code"].strip() and r["gt_item_code"] not in allcodes[r["tenant"]]]
print(" count:", len(bad), bad[:10])

print("\n== T3: gt pointing at disabled / *-OLD items ==")
dis={t:{r["item_code"] for r in rows if r["disabled"]=="1"} for t,rows in cat.items()}
old={t:{r["item_code"] for r in rows if r["item_code"].endswith("-OLD")} for t,rows in cat.items()}
gd=[(r["line_id"],r["gt_item_code"]) for r in train if r["gt_item_code"] in dis.get(r["tenant"],())]
go=[(r["line_id"],r["gt_item_code"]) for r in train if r["gt_item_code"] in old.get(r["tenant"],())]
print(f" disabled items in catalogues: acme={len(dis['acme'])} nordic={len(dis['nordic'])}")
print(f" *-OLD items: acme={len(old['acme'])} nordic={len(old['nordic'])}")
print(f" gt -> disabled: {len(gd)} {gd[:8]}")
print(f" gt -> -OLD:     {len(go)} {go[:8]}")

print("\n== T4: non-item rows in catalogue ==")
for t,rows in cat.items():
    ni=[r["item_code"]+" | "+r["item_name"] for r in rows
        if any(k in r["item_name"].upper() for k in ("DELIVERY","BALANCE","FEE","CHARGE","ROUNDING","DISCOUNT","FREIGHT"))]
    print(f" {t}: {len(ni)}", ni[:8])

print("\n== T5: active twins (same item_name, >1 active code) ==")
for t,rows in cat.items():
    byname=collections.defaultdict(list)
    for r in rows:
        if r["disabled"]!="1": byname[r["item_name"].strip().lower()].append(r["item_code"])
    tw={k:v for k,v in byname.items() if len(v)>1}
    print(f" {t}: {len(tw)} names with >1 active code; total codes involved={sum(len(v) for v in tw.values())}")
    for k,v in list(tw.items())[:5]: print("   ", k, "->", v)
