import json,re
from collections import Counter
exec(open("score_v2.py",encoding="utf-8").read().split("def summ")[0])   # laedt V (Jais-Urteile)
J=V
Q={
("FIQH_001","hanafi","belegt"):"RFF",("FIQH_001","maliki","belegt"):"PFF",("FIQH_001","shafii","belegt"):"RRR",("FIQH_001","hanbali","indirekt"):"RRR",
("FIQH_001","ibn_baz","belegt"):"FFF",("FIQH_001","ibn_uthaymin","belegt"):"FFF",
("FIQH_002","hanafi","belegt"):"RRR",("FIQH_002","maliki","belegt"):"FRR",("FIQH_002","shafii","belegt"):"FRR",("FIQH_002","hanbali","belegt"):"RRR",("FIQH_002","ibn_baz","belegt"):"RRR",
("FIQH_003","maliki","belegt"):"RFR",("FIQH_003","shafii","belegt"):"FFF",("FIQH_003","ibn_baz","belegt"):"RRF",("FIQH_003","ibn_uthaymin","belegt"):"RRF",
("FIQH_004","hanafi","indirekt"):"PPP",("FIQH_004","maliki","belegt"):"FFF",("FIQH_004","shafii","indirekt"):"RRR",("FIQH_004","hanbali","indirekt"):"RRF",("FIQH_004","ibn_baz","belegt"):"RRF",
("FIQH_005","hanafi","indirekt"):"FPR",("FIQH_005","maliki","belegt"):"FFR",("FIQH_005","shafii","belegt"):"RRR",("FIQH_005","hanbali","belegt"):"FFF",("FIQH_005","ibn_baz","belegt"):"FFP",("FIQH_005","ibn_uthaymin","belegt"):"FFF",
("FIQH_006","hanafi","belegt"):"FFF",("FIQH_006","maliki","belegt"):"RRR",("FIQH_006","shafii","indirekt"):"RRR",("FIQH_006","hanbali","indirekt"):"RRR",("FIQH_006","ibn_baz","belegt"):"NRR",("FIQH_006","ibn_uthaymin","belegt"):"NRR",
("FIQH_007","hanafi","belegt"):"FNN",("FIQH_007","maliki","belegt"):"FNN",("FIQH_007","shafii","belegt"):"RNN",("FIQH_007","hanbali","belegt"):"RNN",("FIQH_007","ibn_baz","belegt"):"RNN",
("FIQH_008","hanafi","belegt"):"FFF",("FIQH_008","maliki","indirekt"):"RRR",("FIQH_008","shafii","indirekt"):"RRR",("FIQH_008","hanbali","indirekt"):"RRR",("FIQH_008","ibn_uthaymin","belegt"):"RRR",
("FIQH_009","hanafi","belegt"):"FRR",("FIQH_009","maliki","belegt"):"FRF",("FIQH_009","shafii","belegt"):"RRR",("FIQH_009","hanbali","belegt"):"RRR",("FIQH_009","ibn_baz","belegt"):"RRR",("FIQH_009","ibn_uthaymin","indirekt"):"RRR",
("FIQH_010","hanafi","belegt"):"RRR",("FIQH_010","maliki","belegt"):"FRR",("FIQH_010","shafii","belegt"):"RRR",("FIQH_010","hanbali","belegt"):"FFF",("FIQH_010","ibn_baz","belegt"):"RRR",("FIQH_010","ibn_uthaymin","belegt"):"RRR",
}
def cnt(D,filt):
    c=Counter()
    for k,s in D.items():
        if filt(k):
            for ch in s: c[ch]+=1
    n=sum(c[x] for x in "RFPN"); return c,n
common=[k for k in Q if k in J]
print("gemeinsame Zellen:",len(common))
for lab,filt in (("alle gemeinsamen",lambda k:True),("nur direkt belegt",lambda k:k[2]=="belegt")):
    for name,D in (("Jais ",J),("Qwen ",Q)):
        c,n=cnt({k:D[k] for k in common},filt)
        print(f"{lab:18} {name} gueltige Antworten {n:3} | R {c['R']:3} ({100*c['R']/n:.0f}%) P {c['P']} F {c['F']} N {c['N']} | ungueltig {c['-']}")
# nur Laeufe, in denen Jais gueltig war (fairer Paarvergleich)
rj=rq=n=0
for k in common:
    for a,b in zip(J[k],Q[k]):
        if a in "RFPN": 
            n+=1; rj+= a=="R"; rq+= b=="R"
print(f"Paarvergleich (nur wo Jais gueltig): n={n} Jais R {rj} ({100*rj/n:.0f}%) | Qwen R {rq} ({100*rq/n:.0f}%)")
print("\nQwen pro Stimme (alle Zellen):")
for v in ("hanafi","maliki","shafii","hanbali","ibn_baz","ibn_uthaymin"):
    c,n=cnt(Q,lambda k:k[1]==v); cj,nj=cnt({k:J[k] for k in common},lambda k:k[1]==v)
    print(f"  {v:13} Qwen R {c['R']}/{n} ({100*c['R']/n:.0f}%) | Jais R {cj['R']}/{nj} ({100*cj['R']/nj:.0f}%)")
# Kollaps: alle Stimmen gleiche Antwort
def norm(s): return re.sub(r"\s+"," ",re.sub(r"[ً-ٟ]","",str(s))).strip().lower()
def collapse(path,key):
    d=json.load(open(path,encoding="utf-8")); tot=col=0
    for x in d:
        p=x.get(key) or x.get("parsed")
        if not p or x["id"].startswith("FIQH_C"): continue
        vs=[norm((p.get(v) or {}).get("ruling")) for v in ("hanafi","maliki","shafii","hanbali") if isinstance(p.get(v),dict)]
        vs=[v for v in vs if v not in ("none","null","")]
        if len(vs)<4: continue
        tot+=1; col+= len(set(vs))==1
    return col,tot
print("\nKollaps (4 Schulen, identischer Wortlaut):")
print(" Qwen",collapse("v12/fiqh_runs_v2_qwen.json","parsed"))
print(" Jais",collapse("runs_reparsed.json","parsed_v2"))
