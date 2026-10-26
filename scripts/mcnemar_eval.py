#!/usr/bin/env python3
"""
mcnemar_eval.py - Statistischer Vergleich zweier Modell-Läufe (Baseline A vs B).
Liest die score_*.json Dateien aus dem v3-Scorer und führt den exakten McNemar-Test durch.
"""
import argparse
import json
from scipy import stats

def load_scored_items(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    # v3 Scorer Format: data["details"] ist eine Liste oder Dict
    details = data.get("details", {})
    if isinstance(details, list):
        details = {d["item_id"]: d for d in details}
    
    results = {}
    for item_id, d in details.items():
        v = d.get("verdict", "ERROR")
        # Erfolgskriterien basierend auf v3 Logik
        is_success = v in ["CORRECT", "CORRECT_NEAR", "CORRECT_ABSTENTION", "CORRECT_VARIANT"]
        results[item_id] = is_success
    return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file-a", required=True, help="score JSON Modell A")
    parser.add_argument("--file-b", required=True, help="score JSON Modell B")
    args = parser.parse_args()
    
    res_a = load_scored_items(args.file_a)
    res_b = load_scored_items(args.file_b)
    
    common = set(res_a.keys()) & set(res_b.keys())
    if not common:
        print("Keine gemeinsamen Items!")
        return
        
    a_succ = sum(1 for i in common if res_a[i])
    b_succ = sum(1 for i in common if res_b[i])
    
    # McNemar Kontingenztabelle
    a = b = c = d = 0
    for i in common:
        sa, sb = res_a[i], res_b[i]
        if sa and sb: a += 1
        elif sa and not sb: b += 1
        elif not sa and sb: c += 1
        else: d += 1
        
    print(f"Items: {len(common)} | A Success: {a_succ} | B Success: {b_succ}")
    print(f"Matrix: a={a} (beide), b={b} (nur A), c={c} (nur B), d={d} (keiner)")
    
    if b + c == 0:
        print("Keine diskordanten Paare. Exakter p-Wert: 1.0")
        return
        
    # Exakter Binomialtest
    p_val = stats.binomtest(k=b, n=b+c, p=0.5, alternative='two-sided').pvalue
    print(f"Exakter McNemar p-Wert: {p_val:.4f}")
    if p_val < 0.05:
        print("-> SIGNIFIKANTER UNTERSCHIED (alpha=0.05)")
    else:
        print("-> Kein signifikanter Unterschied.")

if __name__ == "__main__":
    main()