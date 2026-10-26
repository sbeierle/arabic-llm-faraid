#!/usr/bin/env python3
"""Auswertung der Phase-A-Erweiterung -> ERGEBNISSE_ERWEITERUNG.md + ext_summary.json. Liest nur *.score.json / *.jsonl / fertility.json (keine GPU)."""
import argparse, json, math, os, sys
from collections import Counter
from scipy.stats import binomtest
GOOD = {"CORRECT", "CORRECT_NEAR", "CORRECT_ABSTENTION", "CORRECT_VARIANT"}
def wilson(k, n, z=1.96):
    if n == 0: return (0.0, 0.0)
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0, c - h), min(1, c + h)
def load(path):
    if not os.path.exists(path): return None
    j = json.load(open(path, encoding="utf-8"))
    if j.get("skipped") or not j["details"]: return None      # Satz bewusst ausgelassen
    return {d["item_id"]: d for d in j["details"]}
def ok(d): return d["verdict"] in GOOD
def frac(r):
    if r is None: return "n/a"
    k, n = sum(ok(d) for d in r.values()), len(r); lo, hi = wilson(k, n)
    return f"{k}/{n} = {100*k/n:.0f}% (CI {100*lo:.0f}-{100*hi:.0f}%)"
def verd(r): return ", ".join(f"{v} {c}" for v, c in sorted(Counter(d["verdict"] for d in r.values()).items())) if r else "n/a"
TESTS = []
def mcn(name, a, b, la, lb):
    """exakter McNemar, gepaart ueber item_id. Gibt Textzeile zurueck und merkt den Test fuer die Bonferroni-Korrektur."""
    if a is None or b is None: return f"- {name}: nicht verfuegbar"
    ids = sorted(set(a) & set(b)); x = sum(1 for i in ids if ok(a[i]) and not ok(b[i])); y = sum(1 for i in ids if not ok(a[i]) and ok(b[i]))
    p = binomtest(x, x + y, 0.5).pvalue if x + y else 1.0
    TESTS.append((name, p)); return f"- {name}: n={len(ids)}, nur {la} richtig: {x}, nur {lb} richtig: {y}, p = {p:.3g}"
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--res", default="results_ext"); ap.add_argument("--out"); a = ap.parse_args()
    out = a.out or os.path.join(a.res, "ERGEBNISSE_ERWEITERUNG.md"); tags = ["qwen3-30b-a3b", "jais3-mova"]; S = {}
    for t in tags:
        for n in ("faraid_s42", "faraid_s43", "faraid_en", "traps_scaled", "traps_control", "tashkeel_on", "tashkeel_off"): S[(t, n)] = load(f"{a.res}/{t}/{n}.score.json")
    L = ["# Phase-A-Erweiterung: Ergebnisse (nur MoE-Paar)", "", "Alle Zahlen stammen aus diesem Lauf. Richtig = deterministischer Scorer, kein LLM-Judge. CI = Wilson 95 %. Paarvergleiche = exakter McNemar ueber dieselben Items.", ""]
    # 1 Fertilitaet
    fp = f"{a.res}/fertility.json"; L += ["## 1. Tokenizer-Fertilitaet (Tokens pro Wort, weniger = guenstiger)", ""]
    if os.path.exists(fp):
        F = json.load(open(fp, encoding="utf-8")); ks = list(F["korpora"]); L += ["| Korpus | " + " | ".join(F["modelle"]) + " |", "|---|" + "---|" * len(F["modelle"])]
        for k in ks: L.append(f"| {k} (n={F['korpora'][k]}) | " + " | ".join(f"{m[k]['tokens_per_word']:.2f} ({m[k]['tpw_ci95'][0]:.2f}-{m[k]['tpw_ci95'][1]:.2f})" for m in F["modelle"].values()) + " |")
        for pair, d in F["paarweise"].items(): L += ["", f"Token-Verhaeltnis {pair}: " + ", ".join(f"{k} {v['ratio']:.2f}x (CI {v['ci95'][0]:.2f}-{v['ci95'][1]:.2f})" for k, v in d.items())]
        L += ["", "Woerter = Leerzeichen-getrennt. Bukhari = Zufallsstichprobe (1500 Hadithe, Seed fest, inkl. Isnad). Fara'id-AR/EN sind inhaltsgleiche, aber nicht wortgleiche Prompts."]
    else: L.append("fertility.json fehlt (Schritt uebersprungen oder fehlgeschlagen, siehe Log).")
    # 2 Fara'id
    L += ["", "## 2. Fara'id: Sprache (EN-Kontrolle) und Seed-Streuung", "", "| Modell | arabisch seed 42 | arabisch seed 43 | englisch seed 42 |", "|---|---|---|---|"]
    for t in tags: L.append(f"| {t} | {frac(S[(t,'faraid_s42')])} | {frac(S[(t,'faraid_s43')])} | {frac(S[(t,'faraid_en')])} |")
    L += ["", "Basislauf arabisch seed 42: " + "; ".join(f"{t}: " + ("aus dem Hauptlauf uebernommen und mit korrigiertem Gold v2 neu bewertet" if os.path.exists(f"{a.res}/{t}/faraid_s42.herkunft") else "in dieser Erweiterung neu gelaufen") for t in tags)]
    L += ["", "Urteilsverteilung (zeigt, ob Fehler Rechenfehler oder Format/Abbruch sind):", ""]
    for t in tags:
        for n in ("faraid_s42", "faraid_s43", "faraid_en"): L.append(f"- {t} {n}: {verd(S[(t,n)])}")
    L += ["", "Paartests:", ""]
    for t in tags:
        L.append(mcn(f"{t}: englisch vs arabisch (seed 42)", S[(t, 'faraid_en')], S[(t, 'faraid_s42')], "englisch", "arabisch"))
        L.append(mcn(f"{t}: seed 43 vs seed 42 (arabisch)", S[(t, 'faraid_s43')], S[(t, 'faraid_s42')], "seed43", "seed42"))
    for n, lab in (("faraid_s42", "arabisch s42"), ("faraid_s43", "arabisch s43"), ("faraid_en", "englisch")):
        L.append(mcn(f"Modellvergleich Fara'id {lab}: MoVA vs Qwen3", S[("jais3-mova", n)], S[("qwen3-30b-a3b", n)], "MoVA", "Qwen3"))
    flips = {t: (sum(1 for i in S[(t,'faraid_s42')] if i in (S[(t,'faraid_s43')] or {}) and ok(S[(t,'faraid_s42')][i]) != ok(S[(t,'faraid_s43')][i])) if S[(t,'faraid_s42')] and S[(t,'faraid_s43')] else None) for t in tags}
    L += ["", "Items, deren Urteil zwischen seed 42 und 43 kippt: " + ", ".join(f"{t} {v}/50" if v is not None else f"{t} n/a" for t, v in flips.items()) + ". Seed 43 wurde bewusst NICHT gerechnet (Kosten) -> keine Aussage zur Seed-Streuung moeglich." if all(v is None for v in flips.values()) else ", ".join(f"{t} {v}/50" for t, v in flips.items()) + ". Das ist die untere Schranke fuer Seed-Rauschen (nur 2 Seeds)."]
    # 3 Fallen
    L += ["", "## 3. Skalierte Fallen (50) + Gegenprobe (20 echte Verse)", "", "| Modell | ehrliches Schweigen bei Fallen | Konfabulation | Gegenprobe: echte Verse richtig | davon Ueberverweigerung |", "|---|---|---|---|---|"]
    for t in tags:
        T, C = S[(t, 'traps_scaled')], S[(t, 'traps_control')]
        conf = f"{sum(d['verdict']=='CONFABULATED' for d in T.values())}/{len(T)}" if T else "n/a"
        refc = f"{sum(d['verdict']=='ABSTAINED' for d in C.values())}/{len(C)}" if C else "n/a"
        L.append(f"| {t} | {frac(T)} | {conf} | {frac(C)} | {refc} |")
    L += ["", "Nach Fallentyp (ehrliches Schweigen):", ""]
    for t in tags:
        T = S[(t, 'traps_scaled')]
        if T:
            for cat in ("trap_hadith_num", "trap_ayah_num", "trap_sura_num"):
                sub = {i: d for i, d in T.items() if d["category"] == cat}; L.append(f"- {t} {cat}: {frac(sub)}")
    L += ["", "Urteilsverteilung: " + "; ".join(f"{t} Fallen: {verd(S[(t,'traps_scaled')])}, Gegenprobe: {verd(S[(t,'traps_control')])}" for t in tags), "", "Paartest:", ""]
    L.append(mcn("Fallen: MoVA vs Qwen3", S[("jais3-mova", 'traps_scaled')], S[("qwen3-30b-a3b", 'traps_scaled')], "MoVA", "Qwen3"))
    L += ["", "**Scorer-Schwaeche:** Als Schweigen zaehlt jede Antwort mit einer Ablehnungsformel - auch wenn danach doch etwas erfunden wird (bei Qwen2.5 im Hauptlauf einmal beobachtet). Deshalb liegt `audit_fallen_manuell.csv` bei: alle als Schweigen gewerteten Antworten mit >400 Zeichen Rohantwort. Diese Liste von Hand pruefen, bevor eine Schweigerate genannt wird.", ""]
    # 4 Tashkeel
    L += ["## 4. Tashkeel: Koranverse mit vs. ohne Zeichen (40 Paare)", "", "| Modell | mit Tashkeel | ohne Tashkeel |", "|---|---|---|"]
    for t in tags: L.append(f"| {t} | {frac(S[(t,'tashkeel_on')])} | {frac(S[(t,'tashkeel_off')])} |")
    L += ["", "Urteilsverteilung: " + "; ".join(f"{t} mit: {verd(S[(t,'tashkeel_on')])}, ohne: {verd(S[(t,'tashkeel_off')])}" for t in tags), "", "Paartests:", ""]
    for t in tags: L.append(mcn(f"{t}: ohne vs mit Tashkeel", S[(t, 'tashkeel_off')], S[(t, 'tashkeel_on')], "ohne", "mit"))
    for n, lab in (("tashkeel_on", "mit"), ("tashkeel_off", "ohne")): L.append(mcn(f"Modellvergleich Verse {lab} Tashkeel: MoVA vs Qwen3", S[("jais3-mova", n)], S[("qwen3-30b-a3b", n)], "MoVA", "Qwen3"))
    L += ["", "Hadith sind NICHT Teil dieses Tests (Quelle praktisch unvokalisiert). Gold ist der Tanzil-Text; abweichende Schreibweise des Modells (z. B. Uthmani-Orthographie) zaehlt als Fehler - betrifft beide Varianten gleich."]
    # 5 Multiple Tests
    m = len(TESTS); L += ["", f"## 5. Mehrfachtest-Korrektur", "", f"{m} Paartests in diesem Bericht -> Bonferroni-Schwelle alpha = 0.05/{m} = {0.05/m:.4f}." if m else "keine Paartests", ""]
    for name, p in TESTS: L.append(f"- {'**signifikant**' if p < 0.05 / m else 'nicht signifikant'} (p = {p:.3g}): {name}")
    L += ["", "## 6. Grenzen (immer mitliefern)", "",
          "- n ist klein (50 / 50 / 20 / 40). Wilson-CIs sind breit; unterschiedliche Sampling-Parameter je Modell (Herstellerempfehlung) bleiben ein Confound.",
          "- Seed-Test: nur 2 Seeds, zeigt Rauschen nur grob. Englisch-Test: Prompt nennt 'Islamic inheritance law (fara'id)' ausdruecklich, der arabische nur implizit.",
          "- Fara'id-Gold mit 6 Regelvarianten; Umariyyatain-Gold ist Mehrheitsmeinung ohne zitierte Quelle (siehe Korrekturbericht v2).",
          "- Fallen sind synthetisch und rein numerisch (Nummer ausserhalb des Bereichs); sie sagen nichts ueber erfundene Textinhalte.",
          "- Fertilitaet misst Tokenizer, nicht Geschwindigkeit oder Qualitaet."]
    open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    json.dump({"tests": [{"name": n, "p": p} for n, p in TESTS], "bonferroni_alpha": (0.05 / m if m else None)}, open(os.path.join(a.res, "ext_summary.json"), "w"), indent=2, ensure_ascii=False)
    # manuelle Pruefliste Fallen
    import csv
    with open(os.path.join(a.res, "audit_fallen_manuell.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["modell", "item_id", "verdict", "laenge", "antwort_anfang"])
        for t in tags:
            p = f"{a.res}/{t}/traps_scaled.jsonl"
            if not os.path.exists(p): continue
            v = S[(t, 'traps_scaled')] or {}
            for l in open(p, encoding="utf-8"):
                r = json.loads(l); raw = r.get("raw_response", "")
                if "</think>" in raw: raw = raw.rsplit("</think>", 1)[1]
                if v.get(r["item_id"], {}).get("verdict") == "CORRECT_ABSTENTION" and len(raw) > 400: w.writerow([t, r["item_id"], "CORRECT_ABSTENTION", len(raw), raw[:300].replace("\n", " ")])
    print("[+]", out)
if __name__ == "__main__": main()
