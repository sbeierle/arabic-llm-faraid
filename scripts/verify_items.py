#!/usr/bin/env python3
"""Unabhaengige Pruefung: (1) Ground Truth steht woertlich in der Quelle, (2) SHA-256 stimmt, (3) Traps sind in keiner Quelle,
(4) Test- und Kalibrierset sind disjunkt, (5) keine doppelten IDs/Prompts. Exit 1 bei jedem Fehler."""
import csv, json, sys, hashlib
from arnorm import norm
import build_hadith_items as B
def load(p): return list(csv.DictReader(open(p, encoding="utf-8-sig")))
test = load(B.OUT + "islamic_eval_dataset.csv"); cal = load(B.OUT + "calibration_set.csv")
errs = []
allq = " ".join(nt for *_, nt in B.QV)
allh = {k: " ".join(t for _, t in v) for k, v in B.HN.items()}
for r in test + cal:
    gt = r["ground_truth_full_ar"] or r["prompt_ar"] if r["expected_behavior"] == "answer" else None
    if r["expected_behavior"] == "answer":
        full = r["ground_truth_full_ar"]
        if hashlib.sha256(full.encode()).hexdigest() != r["sha256"]: errs.append((r["item_id"], "sha256"))
        n = norm(full)
        if r["category"].startswith("hadith"):
            if not any(n in allh[k] or norm(full) in allh[k] for k in ("riyad",)): errs.append((r["item_id"], "matn nicht in Riyad"))
            if "bukhari=[]" in r["source_ref"] and "muslim=[]" in r["source_ref"]: errs.append((r["item_id"], "nicht in Sahihayn"))
        else:
            s, a = map(int, r["source_ref"].split(":"))
            if not any(S == s and A == a and t == full for S, A, t, _ in B.QV): errs.append((r["item_id"], "Vers != Tanzil"))
        stem = r["prompt_ar"].split("«", 1)[1].rsplit("»", 1)[0]
        if r["category"].startswith("quran") and not r["source_ref"].startswith(("1:", "9:")) and r["source_ref"].endswith(":1") and "بسم الله" in norm(stem): errs.append((r["item_id"], "Basmala im Prompt"))
        rebuilt = norm(stem + " " + r["ground_truth_ar"]); fulln = n
        if "Basmala" in r["note"]: fulln = norm(full.split(" ", 4)[4])  # ohne 4-Wort-Basmala
        if rebuilt != fulln: errs.append((r["item_id"], "stem+continuation != full"))
    else:
        meta = json.loads(r["note"]); ok, desc = B.check_trap(meta["fake"], tuple(meta["chk"]) if meta["chk"] else None)
        if not ok: errs.append((r["item_id"], "Trap ist real vorhanden: " + desc))
ids = [r["item_id"] for r in test + cal]
if len(ids) != len(set(ids)): errs.append(("*", "doppelte item_id"))
tp = {r["prompt_ar"] for r in test}; cp = {r["prompt_ar"] for r in cal}
if tp & cp: errs.append(("*", f"Prompt-Ueberlapp Test/Kalibrierung: {tp & cp}"))
tr = {r["source_ref"].split("riyad idInBook=")[1].split(" ")[0] for r in test if "riyad idInBook=" in r["source_ref"]}
cr = {r["source_ref"].split("riyad idInBook=")[1].split(" ")[0] for r in cal if "riyad idInBook=" in r["source_ref"]}
if tr & cr: errs.append(("*", f"gleicher Hadith in Test+Kal: {tr & cr}"))
tq = {r["source_ref"] for r in test if r["category"].startswith("quran")}; cq = {r["source_ref"] for r in cal if r["category"].startswith("quran")}
if tq & cq: errs.append(("*", f"gleicher Vers in Test+Kal: {tq & cq}"))
print(f"geprueft: {len(test)} Test, {len(cal)} Kalibrierung; Fehler: {len(errs)}")
for e in errs: print("  FEHLER", e)
sys.exit(1 if errs else 0)
