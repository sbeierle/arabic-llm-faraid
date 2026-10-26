#!/usr/bin/env python3
"""Fasst results/<modell>/*.score.json zu einer Tabelle zusammen (Konsole + SUMMARY.md)."""
import argparse, glob, json, os, statistics, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
ap = argparse.ArgumentParser(); ap.add_argument("--results", default="results"); a = ap.parse_args()
models = sorted(d for d in os.listdir(a.results) if os.path.isdir(os.path.join(a.results, d)))
def load(m, n):
    p = os.path.join(a.results, m, n + ".score.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None
def pct(h):
    return "–" if not h else f"{100*h['rate']:.0f}% ({h['k']}/{h['n']}; CI {100*h['ci95'][0]:.0f}-{100*h['ci95'][1]:.0f}%)"
def speed(m):
    ttft, tps = [], []
    for n in ("islamic", "faraid"):
        p = os.path.join(a.results, m, n + ".jsonl")
        if not os.path.exists(p): continue
        for l in open(p, encoding="utf-8"):
            r = json.loads(l)
            if r.get("status") != "success" or r.get("concurrency", 1) != 1: continue   # nur Einzelanfragen sind Latenzmessungen
            ttft.append(r["metrics"]["ttft_ms"]); u = (r.get("usage") or {}).get("completion_tokens")
            dt = (r["metrics"]["total_ms"] - r["metrics"]["ttft_ms"]) / 1000
            if u and dt > 0: tps.append(u / dt)
    return (f"{statistics.median(ttft):.0f} ms" if ttft else "–", f"{statistics.median(tps):.1f}" if tps else "–")
def samp(m):
    p = os.path.join(a.results, m, "islamic.jsonl")
    try:
        r = json.loads(open(p, encoding="utf-8").readline()); d = r.get("sampling") or {}
    except Exception:
        return "–"
    return "greedy" if d.get("temperature", 0.0) == 0.0 else "T=%s P=%s K=%s" % (d.get("temperature"), d.get("top_p", "–"), d.get("top_k", "–"))
rows = []
for m in models:
    st = open(os.path.join(a.results, m, "STATUS")).read().strip() if os.path.exists(os.path.join(a.results, m, "STATUS")) else "?"
    isl, far = load(m, "islamic"), load(m, "faraid")
    hi = (isl or {}).get("headline", {}); hf = (far or {}).get("headline", {})
    over = (isl or {}).get("groups", {}).get("texttreue", {}).get("ABSTAINED", 0)
    nt = hi.get("texttreue", {}).get("n", 0)
    pf = (far or {}).get("groups", {}).get("faraid_core", {}).get("PARSE_FAIL", 0)
    t, s = speed(m)
    rows.append([m, st, pct(hi.get("texttreue")), f"{over}/{nt}" if nt else "–", pct(hi.get("konfabulationsrate")),
                 pct(hf.get("faraid_core")), pct(hf.get("faraid_disputed")), str(pf), samp(m), t, s])
H = ["Modell", "Status", "Hadith/Koran Treffer", "Überverweigerung", "Konfabulation (Fallen)", "Fara'id core exakt", "Fara'id disputed (Variante)", "Fara'id ohne JSON", "Sampling", "TTFT median", "Tok/s (1 Anfrage)"]
md = ["# Phase A – Ergebnisse", "", "| " + " | ".join(H) + " |", "|" + "---|" * len(H)] + ["| " + " | ".join(r) + " |" for r in rows]
md += ["", "Hinweise: n ist klein (25 Texttreue/Fallen, 36+14 Fara'id) – Konfidenzintervalle beachten. Konfabulation = Regex-Erkennung der Verweigerung;",
       "vor dem Zitieren die *.audit.csv stichprobenartig lesen. TTFT/Tok/s nur aus Einzelanfragen (CONC=1), sonst „–“; KEIN Durchsatzbenchmark."]
open(os.path.join(a.results, "SUMMARY.md"), "w", encoding="utf-8").write("\n".join(md) + "\n"); print("\n".join(md))
