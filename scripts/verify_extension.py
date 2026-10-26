#!/usr/bin/env python3
"""Unabhaengige Pruefung der Erweiterungs-Items (liest die Quelldaten selbst, nutzt NICHT den Code des Builders). Exit 1 bei jedem Fehler."""
import csv, json, os, re, sys
from collections import Counter
ROOT = os.environ.get("ARABIC_BENCH_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
I, R = ROOT + "/data/items/", ROOT + "/data/raw/"
def rd(n): return list(csv.DictReader(open(I + n, encoding="utf-8-sig")))
err = []
def need(c, m):
    if not c: err.append(m)
Q = json.load(open(R + "quran-json/data/tanzil/simple.json", encoding="utf-8"))
VERSES = {(int(s), v["verse"]): v["text"] for s, vs in Q.items() for v in vs}
NV = {int(s): len(vs) for s, vs in Q.items()}
need(len(VERSES) == 6236 and len(NV) == 114, "Tanzil-Struktur")
MARK = re.compile("[ً-ٰٟۖ-ۭـ]")
def plain(s): return re.sub(r"\s+", " ", MARK.sub("", s).replace("ٱ", "ا")).strip()
def hmax(book): return max(h["idInBook"] for h in json.load(open(R + f"hadith-json/db/by_book/the_9_books/{book}.json", encoding="utf-8"))["hadiths"])

# Fallen
T = rd("traps_scaled.csv"); need(len(T) == 50, "traps_scaled n"); need(len({r["prompt_ar"] for r in T}) == 50, "traps doppelt")
cnt = Counter(r["category"] for r in T); need(cnt == {"trap_hadith_num": 20, "trap_ayah_num": 20, "trap_sura_num": 10}, f"trap-Kategorien {cnt}")
for r in T:
    chk = json.loads(r["note"])["chk"]; kind = chk[0]
    need(r["expected_behavior"] == "abstain", r["item_id"] + " expected")
    nums = [int(x) for x in re.findall(r"\d+", r["prompt_ar"])]
    if kind == "hadith":
        need(chk[2] in nums and chk[2] > 50000 and chk[2] > hmax(chk[1]), r["item_id"] + " Hadith-Nr")
    elif kind == "ayah":
        need(chk[2] in nums and chk[2] > NV[chk[1]], r["item_id"] + " Vers-Nr")
    elif kind == "sura":
        need(chk[2] in nums and chk[2] > 114, r["item_id"] + " Sure")
    else: need(False, r["item_id"] + " kind")
# Gegenprobe
C = rd("traps_control.csv"); need(len(C) == 20 and len({r["prompt_ar"] for r in C}) == 20, "control n")
for r in C:
    s, a = map(int, r["source_ref"].split(":")); need(VERSES[(s, a)] == r["ground_truth_ar"] and a >= 2, r["item_id"] + " Vers")
# Tashkeel
ON, OFF = rd("quran_tashkeel_on.csv"), rd("quran_tashkeel_off.csv"); need(len(ON) == len(OFF) == 40, "tashkeel n")
allnorm = [plain(t) for t in VERSES.values()]
for a, b in zip(ON, OFF):
    need(a["item_id"] == b["item_id"] and a["ground_truth_ar"] == b["ground_truth_ar"], a["item_id"] + " Paar")
    s, v = map(int, a["source_ref"].split(":")); full = VERSES[(s, v)]
    stem_on = re.search("«(.*)»", a["prompt_ar"]).group(1); stem_off = re.search("«(.*)»", b["prompt_ar"]).group(1)
    need(full.startswith(stem_on) and (stem_on + " " + a["ground_truth_ar"]) == full, a["item_id"] + " Gold=Rest des Verses")
    need(not MARK.search(stem_off) and stem_off == plain(stem_on), a["item_id"] + " ohne-Variante")
    need(bool(MARK.search(stem_on)), a["item_id"] + " mit-Variante hat keine Zeichen")
    need(sum(1 for t in allnorm if re.search(r"(?<!\w)" + re.escape(stem_off) + r"(?!\w)", t)) == 1, a["item_id"] + " Anfang nicht eindeutig")
# Fara'id englisch: gleiche Items/Gold wie arabisch
AR, EN = rd("faraid_eval_dataset.csv"), rd("faraid_en_dataset.csv"); need(len(AR) == len(EN) == 50, "faraid n")
for a, b in zip(AR, EN):
    need(a["item_id"] == b["item_id"] and a["ground_truth_ar"] == b["ground_truth_ar"] and a["variants_json"] == b["variants_json"] and a["category"] == b["category"], a["item_id"] + " EN-Gold")
    need(not re.search("[؀-ۿ]", b["prompt_ar"]), a["item_id"] + " EN-Prompt enthaelt Arabisch")
    keys = re.search(r"English keys: (.*?) \(the value", b["prompt_ar"]).group(1).split(", ")
    keys_ar = re.search(r"التالية: (.*?) \(القيمة", a["prompt_ar"]).group(1).split(", ")
    need(keys == keys_ar, a["item_id"] + f" Schluessel {keys} != {keys_ar}")
# keine Prompt-Kollisionen zwischen allen CSVs (Attrappe/Zuordnung)
allp = Counter(r["prompt_ar"] for n in os.listdir(I) if n.endswith(".csv") and n != "quran_tashkeel_off.csv" for r in rd(n))
need(not [p for p, c in allp.items() if c > 1], "doppelte Prompts ueber CSVs")
if err:
    print("FEHLER:\n  " + "\n  ".join(err[:30])); sys.exit(1)
print("Erweiterungs-Items geprueft: 50 EN-Fara'id, 50 Fallen, 20 Gegenproben, 40 Tashkeel-Paare. Fehler: 0")
