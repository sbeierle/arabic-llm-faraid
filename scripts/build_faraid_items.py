#!/usr/bin/env python3
"""Erzeugt Fara'id-Items. Prompt UND Gold kommen aus derselben Heirs-Struktur (kein handgeschriebener Prompt -> kein Auseinanderlaufen).
Kategorien: faraid_core (Ergebnis unabhaengig von umstrittenen Regeln) | faraid_disputed (Ergebnis haengt von Regel ab; alle Varianten im Gold).
Deterministisch (Seed). Ausgabe: data/items/faraid_eval_dataset.csv (+ faraid_calibration_dataset.csv ist NICHT noetig: Fara'id wird nicht fuer Schwellen genutzt)."""
import csv, hashlib, itertools, json, os, random
from dataclasses import asdict
from fractions import Fraction as F
from faraid_core import Heirs, classify, to_gold, VARIANTS, vname

ROOT = os.environ.get("ARABIC_BENCH_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "data", "items", "faraid_eval_dataset.csv")
DATE = os.environ.get("BENCH_DATE", "2026-10-22")
SEED = 20261022
N_CORE_PER_TAG, N_DISPUTED = 6, 14

def ar_count(n, one, two, plural_word, few=None):
    if n == 1: return one
    if n == 2: return two
    return f"{n} {plural_word}"
def phrases(h: Heirs):
    p = []
    if h.husband: p.append("زوج")
    if h.wives: p.append(ar_count(h.wives, "زوجة", "زوجتين", "زوجات"))
    if h.father: p.append("أب")
    if h.mother: p.append("أم")
    if h.grandfather: p.append("جد (أبو الأب)")
    if h.maternal_grandmother: p.append("جدة لأم (أم الأم)")
    if h.paternal_grandmother: p.append("جدة لأب (أم الأب)")
    if h.sons: p.append(ar_count(h.sons, "ابن", "ابنين", "أبناء"))
    if h.daughters: p.append(ar_count(h.daughters, "بنت", "بنتين", "بنات"))
    if h.full_brothers: p.append(ar_count(h.full_brothers, "أخ شقيق", "أخوين شقيقين", "إخوة أشقاء"))
    if h.full_sisters: p.append(ar_count(h.full_sisters, "أخت شقيقة", "أختين شقيقتين", "أخوات شقيقات"))
    return p
KEYS = lambda h: [k for k, v in asdict(h).items() if k != "deceased" and v]
def prompt_of(h: Heirs):
    verb = "توفي رجل عن" if h.deceased == "male" else "توفيت امرأة عن"
    items = phrases(h)
    heirs_txt = "، و".join(items)
    return (f"{verb}: {heirs_txt}. وليس له وارث غيرهم." if h.deceased == "male" else f"{verb}: {heirs_txt}. وليس لها وارث غيرهم.") + \
           " بيّن نصيب كل وارث كسراً من التركة، مع بيان الحجب والعول والرد إن وُجدت. " \
           "اكتب الجواب النهائي في آخر سطر بصيغة JSON بالمفاتيح الإنجليزية التالية: " + ", ".join(KEYS(h)) + \
           ' (القيمة كسر مثل "1/6" لنصيب المجموعة كاملة وليس الفرد؛ المحجوب "0"؛ وإن بقي شيء لبيت المال فأضف المفتاح bayt_al_mal).'

def enumerate_heirs():
    for dec in ("male", "female"):
        for sp in ([False] if dec == "male" else [False, True]):
            for wv in ([0, 1, 2] if dec == "male" else [0]):
                for fa, mo, gf in itertools.product([0, 1], [0, 1], [0, 1]):
                    if fa and gf: continue
                    for gm in [(0, 0), (1, 0), (0, 1), (1, 1)]:
                        for (so, da) in [(0, 0), (1, 0), (0, 1), (0, 2), (1, 1), (2, 1), (2, 0)]:
                            for (fb, fs) in [(0, 0), (1, 0), (0, 1), (0, 2), (1, 1), (2, 1), (3, 0)]:
                                h = Heirs(dec, sp, wv, bool(fa), bool(mo), bool(gf), bool(gm[0]), bool(gm[1]), so, da, fb, fs)
                                ntypes = sum(1 for k, v in asdict(h).items() if k != "deceased" and v)
                                if ntypes > 5: continue   # realistische, lesbare Faelle
                                try: kind = classify(h, legacy=True)[0]
                                except ValueError: continue
                                if kind != "unsupported": yield h
def tags_of(h, kind, res):
    t = []
    if kind == "disputed": return ["disputed"]
    f = res["flags"]
    for k in ("awl", "radd", "umariyyatain", "hajb", "asaba_maa_ghayr", "bayt_al_mal"):
        if f[k]: t.append(k)
    return t or ["plain"]

def sha(s): return hashlib.sha256(s.encode("utf-8")).hexdigest()
FIELDS = ["item_id","category","prompt_ar","ground_truth_ar","ground_truth_full_ar","expected_behavior","source_name","source_ref","source_url",
          "retrieval_date","license","sha256","note","constellation_json","disputed","variants_json","features"]

def main():
    rnd = random.Random(SEED)
    pool = list(enumerate_heirs()); rnd.shuffle(pool)
    by_tag, disputed = {}, []
    for h in pool:
        kind, res = classify(h, legacy=True)       # Auswahl wie in v1 (damit die 50 Items/Prompts gleich bleiben)
        if kind == "disputed": disputed.append((h, res)); continue
        for t in tags_of(h, kind, res):
            by_tag.setdefault(t, []).append((h, res))
    chosen, seen = [], set()
    for t in ("plain", "hajb", "awl", "radd", "umariyyatain", "asaba_maa_ghayr", "bayt_al_mal"):
        n = 0
        for h, res in by_tag.get(t, []):
            if h in seen: continue
            seen.add(h); chosen.append((h, "undisputed", res)); n += 1
            if n >= N_CORE_PER_TAG: break
    for h, res in disputed[:N_DISPUTED]: chosen.append((h, "disputed", res))
    rows = []
    for i, (h, lkind, lres) in enumerate(chosen, 1):
        kind, res = classify(h)                     # Gold/Varianten mit ALLEN Regelvarianten (inkl. radd=none)
        feats = "|".join(tags_of(h, lkind, lres))
        if kind == "undisputed":
            gold = to_gold(res); variants = {}
        else:
            variants = {vname(k): to_gold(v) for k, v in res.items()}
            gold = to_gold(res[VARIANTS[0]])
            if lkind == "undisputed": feats += "|radd_disputed"
        gj = json.dumps(gold, ensure_ascii=False, sort_keys=True)
        rows.append(dict(item_id=f"FAR{i:03d}", category="faraid_core" if kind == "undisputed" else "faraid_disputed",
            prompt_ar=prompt_of(h), ground_truth_ar=gj, ground_truth_full_ar=gj, expected_behavior="fraction_match",
            source_name="faraid_core.py (exakt, fractions.Fraction; Lehrbuchfaelle in test_faraid_core.py)", source_ref="berechnet",
            source_url="", retrieval_date=DATE, license="eigene Berechnung (Rechenregeln, keine Textvorlage)", sha256=sha(gj),
            note=("Gold = Regel-Variante 'muqasama|radd=blood'; alle 6 Varianten siehe variants_json. Zuordnung Variante->Schule NICHT belegt." if kind == "disputed" else "Ergebnis ist in allen 6 Regelvarianten identisch"),
            constellation_json=json.dumps(asdict(h), sort_keys=True), disputed=str(kind == "disputed"),
            variants_json=json.dumps(variants, ensure_ascii=False, sort_keys=True), features=feats))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, FIELDS); w.writeheader(); w.writerows(rows)
    print(f"{len(rows)} Fara'id-Items ({sum(r['disputed']=='False' for r in rows)} core, {sum(r['disputed']=='True' for r in rows)} disputed) -> {OUT}")
    from collections import Counter
    print("Features:", dict(Counter(f for r in rows for f in r['features'].split('|'))))
if __name__ == "__main__": main()
