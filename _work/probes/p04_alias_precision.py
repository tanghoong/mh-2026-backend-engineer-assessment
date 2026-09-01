import csv, collections
D="data/"
def rd(f):
    with open(D+f, newline='', encoding='utf-8') as fh: return list(csv.DictReader(fh))
smap=rd("customer_sku_map.csv"); train=rd("order_lines_train.csv")
idx=collections.defaultdict(list)
for r in smap: idx[(r["tenant"],r["customer_id"],r["customer_sku"].strip().lower())].append(r)

print("== ALIAS LANE PRECISION on train, sliced by source & confidence ==")
tab=collections.defaultdict(lambda:[0,0])   # key -> [correct, wrong]
rowsout=[]
for r in train:
    bs=r.get("buyer_sku","").strip()
    if not bs: continue
    k=(r["tenant"],r["customer_id"],bs.lower())
    if k not in idx: continue
    gt=r["gt_item_code"].strip()
    for a in idx[k]:
        ok = (gt!="" and a["item_code"]==gt)
        tab[(a["source"],a["confidence"])][0 if ok else 1]+=1
        tab[("ALL","ALL")][0 if ok else 1]+=1
        rowsout.append((r["line_id"],bs,a["item_code"],gt,a["source"],a["confidence"],a["valid_to"],ok))
for k in sorted(tab):
    c,w=tab[k]; print(f"  {k[0]:<16} conf={k[1]:<5} correct={c:<4} wrong={w:<4} precision={c/(c+w):.1%}")

print("\n== same, sliced by confidence ONLY ==")
t2=collections.defaultdict(lambda:[0,0])
for _,_,_,_,s,cf,_,ok in rowsout: t2[cf][0 if ok else 1]+=1
for k in sorted(t2): c,w=t2[k]; print(f"  conf={k}: correct={c} wrong={w} precision={c/(c+w):.1%}")

print("\n== same, sliced by source ONLY ==")
t3=collections.defaultdict(lambda:[0,0])
for _,_,_,_,s,cf,_,ok in rowsout: t3[s][0 if ok else 1]+=1
for k in sorted(t3): c,w=t3[k]; print(f"  {k}: correct={c} wrong={w} precision={c/(c+w):.1%}")

print("\n== 8 examples where the alias is WRONG ==")
for x in [x for x in rowsout if not x[7]][:8]:
    print("   line=",x[0],"sku=",x[1],"alias->",x[2],"but gt=",x[3],"|",x[4],x[5],"valid_to=",repr(x[6]))
print("\n== 5 examples where alias is RIGHT ==")
for x in [x for x in rowsout if x[7]][:5]:
    print("   line=",x[0],"sku=",x[1],"alias->",x[2],"gt=",x[3],"|",x[4],x[5])
