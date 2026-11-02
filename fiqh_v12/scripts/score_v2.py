import csv
from collections import Counter,defaultdict
# (id, stimme, goldstatus) -> Urteile Lauf1,2,3: R richtig, F falsch, P teilweise, N null/keine Aussage, - ungueltig(abgeschnitten)
V={
("FIQH_001","hanafi","belegt"):"-RR",("FIQH_001","maliki","belegt"):"-RR",("FIQH_001","shafii","belegt"):"-RR",
("FIQH_001","hanbali","indirekt"):"-RR",("FIQH_001","ibn_baz","belegt"):"-NF",("FIQH_001","ibn_uthaymin","belegt"):"-NF",
("FIQH_002","hanafi","belegt"):"RRR",("FIQH_002","maliki","belegt"):"FFR",("FIQH_002","shafii","belegt"):"RRR",
("FIQH_002","hanbali","belegt"):"RRR",("FIQH_002","ibn_baz","belegt"):"RRR",
("FIQH_003","maliki","belegt"):"F-R",("FIQH_003","shafii","belegt"):"R-R",("FIQH_003","ibn_baz","belegt"):"R-R",("FIQH_003","ibn_uthaymin","belegt"):"R-R",
("FIQH_004","maliki","belegt"):"RR-",("FIQH_004","shafii","indirekt"):"RR-",("FIQH_004","hanbali","indirekt"):"RR-",("FIQH_004","ibn_baz","belegt"):"RN-",
("FIQH_005","hanafi","indirekt"):"RFR",("FIQH_005","maliki","belegt"):"RFR",("FIQH_005","shafii","belegt"):"RRR",
("FIQH_005","hanbali","belegt"):"RRR",("FIQH_005","ibn_baz","belegt"):"FPR",
("FIQH_006","hanafi","belegt"):"RRR",("FIQH_006","maliki","belegt"):"RRR",("FIQH_006","shafii","indirekt"):"RRR",
("FIQH_006","hanbali","indirekt"):"RRR",("FIQH_006","ibn_baz","belegt"):"RRR",("FIQH_006","ibn_uthaymin","belegt"):"RRR",
("FIQH_007","hanafi","belegt"):"RRR",("FIQH_007","maliki","belegt"):"RRR",("FIQH_007","shafii","belegt"):"RRR",
("FIQH_007","hanbali","belegt"):"RRR",("FIQH_007","ibn_baz","belegt"):"RRR",
("FIQH_008","hanafi","belegt"):"RRR",("FIQH_008","maliki","indirekt"):"RRR",("FIQH_008","shafii","indirekt"):"RRR",
("FIQH_008","hanbali","indirekt"):"RRF",("FIQH_008","ibn_uthaymin","belegt"):"RRR",
("FIQH_009","hanafi","belegt"):"FFF",("FIQH_009","maliki","belegt"):"RRR",("FIQH_009","shafii","belegt"):"RRR",
("FIQH_009","hanbali","belegt"):"RRR",("FIQH_009","ibn_baz","belegt"):"RRR",("FIQH_009","ibn_uthaymin","indirekt"):"RRR",
("FIQH_010","hanafi","belegt"):"RR-",("FIQH_010","maliki","belegt"):"PR-",("FIQH_010","shafii","belegt"):"RR-",
("FIQH_010","hanbali","belegt"):"FF-",("FIQH_010","ibn_baz","belegt"):"FF-",("FIQH_010","ibn_uthaymin","belegt"):"RR-",
}
def summ(filt,label):
    c=Counter(); 
    for k,s in V.items():
        if filt(k):
            for ch in s: c[ch]+=1
    n=sum(c[x] for x in "RFPN")
    print(f"{label:34} Antworten {n:3} | richtig {c['R']:3} ({100*c['R']/n:.0f}%) teilweise {c['P']} falsch {c['F']} null {c['N']}")
    return c
summ(lambda k:True,"alle gewertet (direkt+indirekt)")
summ(lambda k:k[2]=="belegt","nur direkt belegtes Gold")
summ(lambda k:k[2]=="indirekt","nur indirektes Gold")
for run in (0,1,2):
    c=Counter(s[run] for k,s in V.items() if k[2]=="belegt"); n=sum(c[x] for x in "RFPN")
    print(f" Lauf {run+1} (direkt): gueltig {n}, richtig {c['R']}, teilweise {c['P']}, falsch {c['F']}, null {c['N']}")
print("pro Stimme (direkt belegt):")
for v in ("hanafi","maliki","shafii","hanbali","ibn_baz","ibn_uthaymin"):
    c=Counter(); 
    for k,s in V.items():
        if k[1]==v and k[2]=="belegt":
            for ch in s: c[ch]+=1
    n=sum(c[x] for x in "RFPN"); print(f"  {v:13} {n:2} Antworten: richtig {c['R']}, teilw. {c['P']}, falsch {c['F']}, null {c['N']}")
# Stabilitaet: Felder mit gemischten Urteilen
mix=[(k,s) for k,s in V.items() if len(set(ch for ch in s if ch!='-'))>1]
print("Felder mit wechselnden Urteilen zwischen Laeufen:",len(mix),"von",len(V))
for k,s in mix: print("  ",k[0],k[1],s)
const=[(k,s) for k,s in V.items() if len(set(s.replace('-','')))==1 and s.replace('-','')[0]=="F"]
print("durchgehend falsch:",[(k[0],k[1]) for k,s in const])
w=csv.writer(open("fiqh_v2_scoring.csv","w",encoding="utf-8-sig",newline=""),delimiter=";")
w.writerow(["ID","Stimme","Gold-Status","Lauf1","Lauf2","Lauf3"]); 
for k,s in V.items(): w.writerow([k[0],k[1],k[2],*s])
