#!/usr/bin/env python3
"""Lehrbuchfaelle mit HANDGERECHNETEN Ergebnissen. Jeder Fall: (Erben, Regel, radd_spouses, erwartete Anteile, Bayt al-Mal)."""
import random, sys
from fractions import Fraction as F
from faraid_core import Heirs as H, solve, classify, Unsupported

M, FE = "male", "female"
Z = {}  # leer = Standard
CASES = [
 ("Vater + 2 Toechter",               H(M, father=True, daughters=2), {"father": F(1,3), "daughters": F(2,3)}),
 ("Umariyya: Gatte+Mutter+Vater",     H(FE, husband=True, mother=True, father=True), {"husband": F(1,2), "mother": F(1,6), "father": F(1,3)}),
 ("Ehefrau+Mutter+Vater",             H(M, wives=1, mother=True, father=True), {"wives": F(1,4), "mother": F(1,4), "father": F(1,2)}),
 ("Mutter + 1 Bruder",                H(M, mother=True, full_brothers=1), {"mother": F(1,3), "full_brothers": F(2,3)}),
 ("Mutter + 2 Brueder",               H(M, mother=True, full_brothers=2), {"mother": F(1,6), "full_brothers": F(5,6)}),
 ("Tochter + Bruder",                 H(M, daughters=1, full_brothers=1), {"daughters": F(1,2), "full_brothers": F(1,2)}),
 ("2 Brueder + 1 Schwester",          H(M, full_brothers=2, full_sisters=1), {"full_brothers": F(4,5), "full_sisters": F(1,5)}),
 ("Awl: Gatte + 2 Schwestern",        H(FE, husband=True, full_sisters=2), {"husband": F(3,7), "full_sisters": F(4,7)}),
 ("Awl: Gatte+Mutter+1 Schwester",    H(FE, husband=True, mother=True, full_sisters=1), {"husband": F(3,8), "mother": F(1,4), "full_sisters": F(3,8)}),
 ("Awl: Gatte+Mutter+2 Schwestern",   H(FE, husband=True, mother=True, full_sisters=2), {"husband": F(3,8), "mother": F(1,8), "full_sisters": F(1,2)}),
 ("Awl 13: Gatte+Vater+Mutter+Tochter", H(FE, husband=True, father=True, mother=True, daughters=1), {"husband": F(3,13), "father": F(2,13), "mother": F(2,13), "daughters": F(6,13)}),
 ("Awl 27: Frau+Vater+Mutter+2 Toechter", H(M, wives=1, father=True, mother=True, daughters=2), {"wives": F(1,9), "father": F(4,27), "mother": F(4,27), "daughters": F(16,27)}),
 ("Sohn+Tochter+Mutter+Vater",        H(M, sons=1, daughters=1, mother=True, father=True), {"mother": F(1,6), "father": F(1,6), "sons": F(4,9), "daughters": F(2,9)}),
 ("Radd: Tochter allein",             H(M, daughters=1), {"daughters": F(1)}),
 ("Radd: Tochter + Mutter",           H(M, daughters=1, mother=True), {"daughters": F(3,4), "mother": F(1,4)}),
 ("Radd: Mutter allein",              H(M, mother=True), {"mother": F(1)}),
 ("Radd: Schwester allein",           H(M, full_sisters=1), {"full_sisters": F(1)}),
 ("Radd: 2 Schwestern",               H(M, full_sisters=2), {"full_sisters": F(1)}),
 ("Radd: Mutter + Schwester",         H(M, mother=True, full_sisters=1), {"mother": F(2,5), "full_sisters": F(3,5)}),
 ("Radd: Mutter + 2 Schwestern",      H(M, mother=True, full_sisters=2), {"mother": F(1,5), "full_sisters": F(4,5)}),
 ("Gatte + Schwester",                H(FE, husband=True, full_sisters=1), {"husband": F(1,2), "full_sisters": F(1,2)}),
 ("Grossvater allein",                H(M, grandfather=True), {"grandfather": F(1)}),
 ("Grossvater + Sohn",                H(M, grandfather=True, sons=1), {"grandfather": F(1,6), "sons": F(5,6)}),
 ("2 Grossmuetter",                   H(M, maternal_grandmother=True, paternal_grandmother=True), {"maternal_grandmother": F(1,2), "paternal_grandmother": F(1,2)}),
 ("Mutter sperrt Grossmutter",        H(M, mother=True, paternal_grandmother=True), {"mother": F(1), "paternal_grandmother": F(0)}),
 ("Vater sperrt vaeterl. Grossmutter", H(M, father=True, paternal_grandmother=True), {"father": F(1), "paternal_grandmother": F(0)}),
 ("Vater sperrt NICHT muetterl. Gm",  H(M, father=True, maternal_grandmother=True), {"father": F(5,6), "maternal_grandmother": F(1,6)}),
 ("Mutter+Vater+Bruder (Bruder gesperrt, Mutter 1/3)", H(M, mother=True, father=True, full_brothers=1), {"mother": F(1,3), "father": F(2,3), "full_brothers": F(0)}),
 ("Mutter+Vater+2 Brueder (gesperrte reduzieren Mutter)", H(M, mother=True, father=True, full_brothers=2), {"mother": F(1,6), "father": F(5,6), "full_brothers": F(0)}),
 ("Tochter + Schwester (Asaba ma'a al-Ghayr)", H(M, daughters=1, full_sisters=1), {"daughters": F(1,2), "full_sisters": F(1,2)}),
 ("2 Toechter + Schwester",           H(M, daughters=2, full_sisters=1), {"daughters": F(2,3), "full_sisters": F(1,3)}),
 ("Sohn sperrt Bruder",               H(M, sons=1, full_brothers=1), {"sons": F(1), "full_brothers": F(0)}),
 ("Gatte+Mutter+Grossvater+Bruder (Rest 1/6)", H(FE, husband=True, mother=True, grandfather=True, full_brothers=1), {"husband": F(1,2), "mother": F(1,3), "grandfather": F(1,6), "full_brothers": F(0)}),
]
# Regelabhaengige Faelle: (Name, Erben, Regel, radd_spouses, erwartet, bayt)
RULE_CASES = [
 ("GF+Bruder muqasama",   H(M, grandfather=True, full_brothers=1), "muqasama", False, {"grandfather": F(1,2), "full_brothers": F(1,2)}, F(0)),
 ("GF+Bruder blocks",     H(M, grandfather=True, full_brothers=1), "blocks",   False, {"grandfather": F(1), "full_brothers": F(0)}, F(0)),
 ("GF+Schwester muqasama",H(M, grandfather=True, full_sisters=1),  "muqasama", False, {"grandfather": F(2,3), "full_sisters": F(1,3)}, F(0)),
 ("GF+3 Brueder muqasama (1/3 des Rests)", H(M, grandfather=True, full_brothers=3), "muqasama", False, {"grandfather": F(1,3), "full_brothers": F(2,3)}, F(0)),
 ("GF+Tochter+Bruder muqasama", H(M, grandfather=True, daughters=1, full_brothers=1), "muqasama", False, {"daughters": F(1,2), "grandfather": F(1,4), "full_brothers": F(1,4)}, F(0)),
 ("GF+Tochter+Bruder blocks",   H(M, grandfather=True, daughters=1, full_brothers=1), "blocks",   False, {"daughters": F(1,2), "grandfather": F(1,2), "full_brothers": F(0)}, F(0)),
 ("Ehefrau allein: Bayt al-Mal", H(M, wives=1), "muqasama", False, {"wives": F(1,4)}, F(3,4)),
 ("Ehefrau allein: Radd Ehepartner", H(M, wives=1), "muqasama", True, {"wives": F(1)}, F(0)),
 ("Gatte+Tochter ohne Radd-Ehepartner", H(FE, husband=True, daughters=1), "muqasama", False, {"husband": F(1,4), "daughters": F(3,4)}, F(0)),
 ("Gatte+Tochter mit Radd-Ehepartner",  H(FE, husband=True, daughters=1), "muqasama", True,  {"husband": F(1,3), "daughters": F(2,3)}, F(0)),
]
fails = 0
def chk(name, got, exp, bayt=F(0), gb=F(0)):
    global fails
    if got != exp or gb != bayt:
        fails += 1; print("FAIL", name, "\n   erwartet", {k: str(v) for k, v in exp.items()}, bayt, "\n   erhalten", {k: str(v) for k, v in got.items()}, gb)
for name, h, exp in CASES:
    r = solve(h); chk(name, r["shares"], exp, F(0), r["bayt_al_mal"])
for name, h, g, rs, exp, b in RULE_CASES:
    r = solve(h, g, rs); chk(name, r["shares"], exp, b, r["bayt_al_mal"])
# Akdariyya muss abgelehnt werden
try:
    solve(H(FE, husband=True, mother=True, grandfather=True, full_sisters=1)); fails += 1; print("FAIL Akdariyya nicht abgelehnt")
except Unsupported: pass
# Klassifikation
exp_cls = {"undisputed": [H(M, father=True, daughters=2), H(FE, husband=True, mother=True, father=True)],
           "disputed": [H(M, grandfather=True, full_brothers=1), H(M, wives=1), H(FE, husband=True, daughters=1)]}
for k, hs in exp_cls.items():
    for h in hs:
        c = classify(h)[0]
        if c != k: fails += 1; print("FAIL classify", h, c, "erwartet", k)
# Fuzz: Summe = 1 (assert in solve), keine unerwarteten Exceptions
rnd = random.Random(7); n_ok = n_un = 0
for _ in range(20000):
    dec = rnd.choice([M, FE])
    h = H(dec, husband=(dec == FE and rnd.random() < .5), wives=(rnd.randint(0, 2) if dec == M and rnd.random() < .5 else 0),
          father=rnd.random() < .3, mother=rnd.random() < .5, grandfather=rnd.random() < .2,
          maternal_grandmother=rnd.random() < .2, paternal_grandmother=rnd.random() < .2,
          sons=rnd.choice([0, 0, 1, 2]), daughters=rnd.choice([0, 0, 1, 2, 3]),
          full_brothers=rnd.choice([0, 0, 1, 2]), full_sisters=rnd.choice([0, 0, 1, 2]))
    try: classify(h); n_ok += 1
    except ValueError: pass
    except Exception as e: fails += 1; print("FUZZ-FEHLER", h, repr(e)); break
print(f"{len(CASES)+len(RULE_CASES)} Lehrbuchfaelle + Akdariyya + Klassifikation + Fuzz({n_ok} Konstellationen, Summe==1 intern geprueft). Fehler: {fails}")
sys.exit(1 if fails else 0)
