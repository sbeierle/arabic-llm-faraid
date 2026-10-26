#!/usr/bin/env python3
"""Prueft faraid_eval_dataset.csv unabhaengig: Gold neu berechnen, Prompt neu erzeugen, SHA, Disputed-Flag, Varianten, Eindeutigkeit."""
import csv, json, hashlib, os, sys
from fractions import Fraction as F
from faraid_core import Heirs, classify, to_gold, VARIANTS
from build_faraid_items import prompt_of, OUT
rows = list(csv.DictReader(open(OUT, encoding="utf-8-sig")))
errs = []
for r in rows:
    h = Heirs(**json.loads(r["constellation_json"])); kind, res = classify(h); i = r["item_id"]
    if (kind == "disputed") != (r["disputed"] == "True"): errs.append((i, "disputed-Flag"))
    if kind == "unsupported": errs.append((i, "unsupported Konstellation im Datensatz")); continue
    if prompt_of(h) != r["prompt_ar"]: errs.append((i, "Prompt != neu erzeugt"))
    gold = to_gold(res if kind == "undisputed" else res[VARIANTS[0]])
    if json.dumps(gold, ensure_ascii=False, sort_keys=True) != r["ground_truth_ar"]: errs.append((i, "Gold != neu berechnet"))
    if hashlib.sha256(r["ground_truth_ar"].encode()).hexdigest() != r["sha256"]: errs.append((i, "sha256"))
    if sum(F(v) for k, v in json.loads(r["ground_truth_ar"]).items()) != 1: errs.append((i, "Gold-Summe != 1"))
    if kind == "disputed":
        v = json.loads(r["variants_json"])
        if len({json.dumps(x, sort_keys=True) for x in v.values()}) < 2: errs.append((i, "disputed ohne echte Varianten"))
    elif r["variants_json"] != "{}": errs.append((i, "undisputed mit Varianten"))
ids = [r["item_id"] for r in rows]; pr = [r["prompt_ar"] for r in rows]
if len(set(ids)) != len(ids): errs.append(("*", "doppelte IDs"))
if len(set(pr)) != len(pr): errs.append(("*", "doppelte Prompts"))
print(f"Fara'id geprueft: {len(rows)} Items, Fehler: {len(errs)}")
for e in errs: print("  FEHLER", e)
sys.exit(1 if errs else 0)
