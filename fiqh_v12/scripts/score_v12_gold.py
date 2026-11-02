import json,sys,collections,csv
sys.path.insert(0,".")
from classify import *
rows=[]
for model in ("jais","qwen"):
    R=json.load(open(f"fiqh_v12_results_{model}.json",encoding="utf-8"))
    for x in R:
        if x["suite"]!="RAG": continue
        valid = x.get("finish")=="stop" and bool(x.get("parsed"))
        for (q,v) in GL:
            if q!=x["base_id"]: continue
            if not valid: rows.append((model,x["condition"],q,v,x["run"],"INVALID",""));continue
            o=x["parsed"].get(v); rl=(o or {}).get("ruling") if isinstance(o,dict) else None
            rows.append((model,x["condition"],q,v,x["run"],verdict(q,v,rl),str(rl)[:80].replace("\n"," ")))
with open("fiqh_v12_gold_scoring.csv","w",encoding="utf-8-sig",newline="") as f:
    w=csv.writer(f,delimiter=";"); w.writerow(["Modell","Bedingung","ID","Stimme","Lauf","Urteil","Ruling"]); w.writerows(rows)
T=collections.defaultdict(collections.Counter)
for m,c,q,v,r,u,_ in rows: T[(m,c)][u]+=1
print("Modell | Bedingung | R P F N ? ungueltig | Trefferquote R/(R+P+F) | Null-Quote")
for m in ("jais","qwen"):
    for c in ("NO_CTX","ORACLE","RET_TOP3","WRONG"):
        k=T[(m,c)]; d=k["R"]+k["P"]+k["F"]
        print(f"{m:5}|{c:9}| {k['R']:3} {k['P']:2} {k['F']:3} {k['N']:3} {k['?']:3} {k['INVALID']:3} | {100*k['R']/d if d else 0:5.1f}% (n={d}) | null {100*k['N']/(d+k['N']) if d+k['N'] else 0:4.1f}%")
# Zielfragen vs andere
TG={"FIQH_001","FIQH_003","FIQH_005","FIQH_009","FIQH_010"}
print("\nNur Fehlerfragen 001/003/005/009/010 vs. uebrige, Trefferquote (R/(R+P+F)):")
for m in ("jais","qwen"):
    for grp,name in ((TG,"Fehlerfragen"),(None,"uebrige")):
        out=[]
        for c in ("NO_CTX","ORACLE","RET_TOP3"):
            k=collections.Counter(u for mm,cc,q,v,r,u,_ in rows if mm==m and cc==c and ((q in TG) if grp else (q not in TG)))
            d=k["R"]+k["P"]+k["F"]; out.append(f"{c} {100*k['R']/d:.0f}% (n={d})" if d else f"{c} -")
        print(f" {m:5} {name:13}"," | ".join(out))
