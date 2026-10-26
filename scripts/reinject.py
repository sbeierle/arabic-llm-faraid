#!/usr/bin/env python3
"""Uebernimmt Item-Felder (Kategorie, Gold, Varianten ...) aus einer Item-CSV in eine vorhandene Ergebnis-JSONL (per item_id). Rohantworten bleiben unveraendert.
Zweck: Basislauf (Fara'id seed 42) mit dem korrigierten Gold v2 (Radd-Parameter) neu bewerten, ohne neu zu generieren."""
import argparse, csv, json, sys
ap = argparse.ArgumentParser(); ap.add_argument("--jsonl", required=True); ap.add_argument("--items", required=True); ap.add_argument("--out", required=True); a = ap.parse_args()
items = {r["item_id"]: r for r in csv.DictReader(open(a.items, encoding="utf-8-sig"))}
KEYS = ("category", "ground_truth_ar", "ground_truth_full_ar", "expected_behavior", "note", "disputed", "variants_json", "features", "sha256", "constellation_json")
n = 0
with open(a.out, "w", encoding="utf-8") as f:
    for l in open(a.jsonl, encoding="utf-8"):
        if not l.strip(): continue
        d = json.loads(l)
        it = items.get(d["item_id"])
        if it is None: sys.exit(f"item_id {d['item_id']} nicht in {a.items}")
        if "prompt_ar" in d and d["prompt_ar"] != it["prompt_ar"]: sys.exit(f"Prompt von {d['item_id']} weicht ab - falsche Item-Datei?")
        for k in KEYS:
            if k in it: d[k] = it[k]
        f.write(json.dumps(d, ensure_ascii=False) + "\n"); n += 1
print(f"[+] {n} Records neu zugeordnet -> {a.out}")
