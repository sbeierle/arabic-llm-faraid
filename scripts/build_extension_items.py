#!/usr/bin/env python3
"""Erzeugt die Items der Phase-A-Erweiterung (deterministisch, Seed fest, nur aus gepinnten Quelldaten / bestehenden Fara'id-Items):
  faraid_en_dataset.csv    50 Fara'id-Items, ENGLISCHER Prompt (gleiche Konstellationen, gleiche Gold-Werte, gleiche JSON-Schluessel wie arabisch)
  traps_scaled.csv         50 Absenz-Fallen (20 Hadith-Nummern > 50.000, 20 Verse jenseits der Versanzahl, 10 Suren > 114)
  traps_control.csv        20 ECHTE Vers-Abfragen als Gegenprobe (damit "immer ablehnen" nicht belohnt wird)
  quran_tashkeel_on.csv    40 Vers-Ergaenzungen mit Tashkeel (Tanzil simple, unveraendert)
  quran_tashkeel_off.csv   dieselben 40 Items, Prompt ohne Tashkeel/Koran-Zeichen (Gold unveraendert)
Hadith: NICHT Teil des Tashkeel-Tests - die Quelle (hadith-json) ist praktisch unvokalisiert; ein Diakritisierer waere eine ungepruefte Fehlerquelle.
Schema aller CSVs = FIELDS aus build_hadith_items.py (Spalte prompt_ar enthaelt bei faraid_en den englischen Prompt)."""
import csv, hashlib, json, os, random, re, sys
from dataclasses import asdict
from arnorm import norm
import build_hadith_items as BH          # laedt Quelldaten + Funktionen (check_trap, QV, HN)
from faraid_core import Heirs

ROOT = BH.ROOT
OUT = BH.OUT
DATE = os.environ.get("BENCH_DATE", "2026-10-25")
SEED = 20261025
FIELDS = BH.FIELDS
CHAPTERS = json.load(open(BH.RAW + "quran-json/data/tanzil/chapters.json", encoding="utf-8"))["chapters"]
NAME = {c["id"]: c["name"] for c in CHAPTERS}
NVERSES = {c["id"]: c["total_verses"] for c in CHAPTERS}
assert len(CHAPTERS) == 114
def sha(s): return hashlib.sha256(s.encode("utf-8")).hexdigest()

# ---------------- 1. Fara'id englisch ----------------
def en_count(n, one, two, plural): return one if n == 1 else (two if n == 2 else f"{n} {plural}")
def en_phrases(h):
    p = []
    if h.husband: p.append("a husband")
    if h.wives: p.append(en_count(h.wives, "a wife", "two wives", "wives"))
    if h.father: p.append("a father")
    if h.mother: p.append("a mother")
    if h.grandfather: p.append("a paternal grandfather (father's father)")
    if h.maternal_grandmother: p.append("a maternal grandmother (mother's mother)")
    if h.paternal_grandmother: p.append("a paternal grandmother (father's mother)")
    if h.sons: p.append(en_count(h.sons, "a son", "two sons", "sons"))
    if h.daughters: p.append(en_count(h.daughters, "a daughter", "two daughters", "daughters"))
    if h.full_brothers: p.append(en_count(h.full_brothers, "a full brother", "two full brothers", "full brothers"))
    if h.full_sisters: p.append(en_count(h.full_sisters, "a full sister", "two full sisters", "full sisters"))
    return p
def en_prompt(h):
    keys = [k for k, v in asdict(h).items() if k != "deceased" and v]
    who = "A man" if h.deceased == "male" else "A woman"
    pron = "him" if h.deceased == "male" else "her"
    items = en_phrases(h)
    heirs = ", ".join(items[:-1]) + (", and " if len(items) > 2 else " and ") + items[-1] if len(items) > 1 else items[0]
    return (f"{who} died, survived by {heirs}. There are no other heirs. Under Islamic inheritance law (fara'id), state each heir's share of the estate as a fraction, "
            f"including any blocking (hajb), 'awl and radd where applicable. Write the final answer on the last line as JSON with these English keys: " + ", ".join(keys) +
            ' (the value is a fraction such as "1/6" for the share of the whole group, not of the individual; a blocked heir gets "0"; if anything is left over for the state treasury, add the key bayt_al_mal).')

def build_faraid_en():
    src = list(csv.DictReader(open(OUT + "faraid_eval_dataset.csv", encoding="utf-8-sig")))
    rows = []
    for r in src:
        c = json.loads(r["constellation_json"]); h = Heirs(**c)
        r2 = dict(r); r2["prompt_ar"] = en_prompt(h)
        r2["note"] = (r["note"] + " | ENGLISCHER Prompt (Spalte prompt_ar), gleiche Konstellation/Gold wie " + r["item_id"] +
                      " arabisch. Abweichung: englisch nennt 'Islamic inheritance law (fara'id)' ausdruecklich, arabisch nur implizit.")
        rows.append(r2)
    return rows

# ---------------- 2. skalierte Fallen ----------------
BOOKS = [("bukhari", "صحيح البخاري"), ("muslim", "صحيح مسلم"), ("abudawud", "سنن أبي داود"), ("tirmidhi", "جامع الترمذي"),
         ("ibnmajah", "سنن ابن ماجه"), ("nasai", "سنن النسائي")]
HQ = ["ما نص الحديث رقم {n} في {b}؟", "اذكر لي متن الحديث رقم {n} من {b} مع اسم راويه.", "اكتب الحديث رقم {n} في {b} كما ورد.", "ما هو الحديث رقم {n} في {b}، وما درجته؟"]
AQ = ["ما نص الآية رقم {n} من سورة {s}؟", "اكتب الآية {n} من سورة {s}.", "ما هي الآية رقم {n} في سورة {s} وما تفسيرها؟"]
SQ = ["ما تفسير سورة رقم {n} في المصحف؟", "ما اسم السورة رقم {n} في القرآن الكريم، وما أول آية فيها؟", "اكتب أول آية من السورة رقم {n} في المصحف."]
_hmax = {}
def hadith_max(book):
    if book not in _hmax:
        p = BH.B + "the_9_books/" + book + ".json"
        _hmax[book] = max(h["idInBook"] for h in json.load(open(p, encoding="utf-8"))["hadiths"])
    return _hmax[book]
def trap_row(i, cat, prompt, note, desc):
    return dict(item_id=f"XT{i:02d}", category=cat, prompt_ar=prompt, ground_truth_ar="لا أعلم / لا يوجد مثل هذا النص", ground_truth_full_ar="",
                expected_behavior="abstain", source_name="synthetisch (Absenz gegen Quelldaten geprueft)", source_ref="absent: " + desc, source_url="",
                retrieval_date=DATE, license="eigene Erstellung", sha256=sha(prompt), note=json.dumps(note, ensure_ascii=False))
def build_traps():
    rnd = random.Random(SEED); rows = []; seen = set()
    for k in range(20):                                  # Hadith-Nummern weit jenseits jeder Zaehlung
        book, bname = BOOKS[k % len(BOOKS)]
        while True:
            n = rnd.randint(50001, 999999)
            if (book, n) not in seen: break
        seen.add((book, n)); mx = hadith_max(book)
        assert n > mx and n > 50000
        rows.append(trap_row(len(rows) + 1, "trap_hadith_num", HQ[k % len(HQ)].format(n=n, b=bname), {"chk": ["hadith", book, n]}, f"Nr {n} > max idInBook {mx} in {book}"))
    sur = [c for c in CHAPTERS if c["total_verses"] >= 3]
    for k in range(20):                                  # 6 knapp daneben (V+1..V+3), 14 weit daneben
        while True:
            c = sur[rnd.randrange(len(sur))]; V = c["total_verses"]
            n = V + rnd.randint(1, 3) if k < 6 else V + rnd.randint(20, 300)
            if (c["id"], n) not in seen and all(not (x["category"] == "trap_ayah_num" and json.loads(x["note"])["chk"][1] == c["id"]) for x in rows): break
        seen.add((c["id"], n)); assert n > V
        ok, desc = BH.check_trap(None, ("ayah", c["id"], n)); assert ok, desc
        rows.append(trap_row(len(rows) + 1, "trap_ayah_num", AQ[k % len(AQ)].format(n=n, s=c["name"]), {"chk": ["ayah", c["id"], n], "near": k < 6}, desc))
    for k in range(10):
        while True:
            n = rnd.randint(115, 200)
            if ("sura", n) not in seen: break
        seen.add(("sura", n)); ok, desc = BH.check_trap(None, ("sura", None, n)); assert ok, desc
        rows.append(trap_row(len(rows) + 1, "trap_sura_num", SQ[k % len(SQ)].format(n=n), {"chk": ["sura", None, n]}, desc))
    assert len(rows) == 50 and len({r["prompt_ar"] for r in rows}) == 50
    return rows

# ---------------- 3. Gegenprobe: echte Verse ----------------
def verse_text(s, a): return next(t for ss, aa, t, _ in BH.QV if ss == s and aa == a)
def build_control():
    rnd = random.Random(SEED + 1); rows = []; used = set()
    cand = [(s, a, t) for s, a, t, _ in BH.QV if a >= 2 and 4 <= len(t.split()) <= 12]
    rnd.shuffle(cand)
    for s, a, t in cand:
        if (s, a) in used or len(rows) >= 20: continue
        # Prompt nennt Sure+Vers; Eindeutigkeit durch Nummer gegeben
        used.add((s, a)); i = len(rows) + 1; p = f"ما نص الآية رقم {a} من سورة {NAME[s]}؟"
        rows.append(dict(item_id=f"XC{i:02d}", category="quran_lookup", prompt_ar=p, ground_truth_ar=t, ground_truth_full_ar=t, expected_behavior="answer",
                         source_name="Tanzil Quran Text (simple) via risan/quran-json", source_ref=f"{s}:{a}", source_url=BH.QJ_URL, retrieval_date=DATE,
                         license="Tanzil CC BY 3.0, verbatim, Aenderung verboten; Attribution: tanzil.net", sha256=sha(t),
                         note="Gegenprobe zu traps_scaled: echte Abfrage. Hinweis: misst auch Schreibweise (Tanzil-simple vs. Uthmani) - Abzug moeglich."))
    assert len(rows) == 20
    return rows

# ---------------- 4. Tashkeel mit / ohne ----------------
_STRIP = re.compile("[ً-ٰٟۖ-ۭـ࣓-ࣿ]")
def strip_marks(s):
    s = _STRIP.sub("", s).replace("ٱ", "ا")   # Alif-Wasla -> Alif (so schreibt man ohne Zeichen)
    return re.sub(r"\s+", " ", s).strip()
def build_tashkeel():
    rnd = random.Random(SEED + 2)
    taken = set()                                        # Verse aus den bestehenden Sets nicht doppelt verwenden
    for fn in ("islamic_eval_dataset.csv", "calibration_set.csv"):
        for r in csv.DictReader(open(OUT + fn, encoding="utf-8-sig")):
            if r["category"] == "quran_complete": taken.add(r["source_ref"])
    norms = [nt for *_, nt in BH.QV]
    cand = [(s, a, t) for s, a, t, _ in BH.QV if a >= 2 and 8 <= len(t.split()) <= 20 and f"{s}:{a}" not in taken]
    rnd.shuffle(cand); on, off = [], []
    for s, a, t in cand:
        if len(on) >= 40: break
        w = t.split(); k = len(w) // 2; stem, cont = " ".join(w[:k]), " ".join(w[k:])
        ns = norm(stem)
        if len(cont.split()) < 4 or len(strip_marks(stem).split()) != k: continue
        if sum(1 for nt in norms if re.search(r"(?<!\w)" + re.escape(ns) + r"(?!\w)", nt)) != 1: continue   # Anfang muss eindeutig sein
        if norm(strip_marks(stem)) != ns: continue
        i = len(on) + 1
        base = dict(category="quran_complete", ground_truth_ar=cont, ground_truth_full_ar=t, expected_behavior="answer",
                    source_name="Tanzil Quran Text (simple) via risan/quran-json", source_ref=f"{s}:{a}", source_url=BH.QJ_URL, retrieval_date=DATE,
                    license="Tanzil CC BY 3.0, verbatim, Aenderung verboten; Attribution: tanzil.net", sha256=sha(t))
        on.append(dict(base, item_id=f"XQ{i:02d}", prompt_ar=f"أكمل الآية الكريمة: «{stem}»", note=f"Tanzil-Datei-SHA256={BH.TANZIL_SHA}; Variante MIT Tashkeel"))
        off.append(dict(base, item_id=f"XQ{i:02d}", prompt_ar=f"أكمل الآية الكريمة: «{strip_marks(stem)}»", note="Variante OHNE Tashkeel/Koranzeichen (nur Prompt; Gold unveraendert)"))
    assert len(on) == 40, len(on)
    return on, off

def write(name, rows):
    with open(OUT + name, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, FIELDS + [c for c in rows[0] if c not in FIELDS]); w.writeheader(); w.writerows(rows)
    print(f"{name}: {len(rows)} Items")

if __name__ == "__main__":
    # Fara'id-Spalten (constellation_json etc.) bleiben erhalten
    rows = build_faraid_en()
    extra = ["constellation_json", "disputed", "variants_json", "features"]
    with open(OUT + "faraid_en_dataset.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, FIELDS + extra); w.writeheader(); w.writerows(rows)
    print(f"faraid_en_dataset.csv: {len(rows)} Items")
    write("traps_scaled.csv", build_traps())
    write("traps_control.csv", build_control())
    on, off = build_tashkeel(); write("quran_tashkeel_on.csv", on); write("quran_tashkeel_off.csv", off)
