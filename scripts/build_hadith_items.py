#!/usr/bin/env python3
"""Baut Hadith-/Quran-/Trap-Items (Test + Kalibrierung) AUS DEN QUELLDATEN, nicht aus dem Gedaechtnis.
Regeln: Anker (Textfragment) muss in Riyad as-Salihin GENAU 1x und in Bukhari/Muslim >=1x treffen.
Ground Truth = unveraenderter Quelltext. Normalisierung nur fuer die Suche."""
import json, csv, hashlib, re, sys, os
from arnorm import norm
ROOT = os.environ.get("ARABIC_BENCH_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW = os.path.join(ROOT, "data", "raw") + os.sep
OUT = os.path.join(ROOT, "data", "items") + os.sep
DATE = "2026-10-22"
HJ_COMMIT = "70b83d6d21995bb32f8d7271cd75501be5a922a7"
QJ_COMMIT = "6523a9ad3b73bb7e8cb3a9cdf0ea774b8bab3123"
HJ_URL = "https://github.com/AhmedBaset/hadith-json/tree/" + HJ_COMMIT + "/db/by_book/"
QJ_URL = "https://github.com/risan/quran-json/tree/" + QJ_COMMIT + "/data/tanzil/simple.json"
TANZIL_SHA = "703246a73a0a3d57f721b02e3edad9a2ee6831b79f49ffb9513ddfe99a65b801"  # laut quran-json meta/sources.json

B = RAW + "hadith-json/db/by_book/"
books = {"riyad": B + "other_books/riyad_assalihin.json", "bukhari": B + "the_9_books/bukhari.json", "muslim": B + "the_9_books/muslim.json"}
H = {k: json.load(open(p, encoding="utf-8"))["hadiths"] for k, p in books.items()}
HN = {k: [(h["idInBook"], norm(h["arabic"])) for h in v] for k, v in H.items()}
Q = json.load(open(RAW + "quran-json/data/tanzil/simple.json", encoding="utf-8"))
QV = [(int(s), v["verse"], v["text"], norm(v["text"])) for s, vs in Q.items() for v in vs]
assert len(QV) == 6236, len(QV)

# ---- Anker-Konfiguration (Textfragmente, normalisiert geschrieben) ----
TEST_H = ["الاعمال بالنيات","الدين النصيحة","حتى يحب لاخيه ما يحب لنفسه","خيركم من تعلم القران وعلمه","الطهور شطر الايمان",
          "دعه فان الحياء من الايمان","من كذب علي متعمدا فليتبوا مقعده","بني الاسلام على خمس","المسلم من سلم المسلمون من لسانه ويده",
          "كلمتان خفيفتان على اللسان","ان الدين يسر","من دل على خير فله مثل اجر فاعله"]
CAL_H = ["ليس الشديد بالصرعه","من سلك طريقا يلتمس فيه علما","اتقوا النار ولو بشق تمره","فاذا نهيتكم عن شيء فاجتنبوه",
         "من لا يرحم لا يرحم","الكلمه الطيبه صدقه","لا تغضب","الدنيا سجن المومن وجنه الكافر"]
TEST_Q = ["الله لا اله الا هو الحي القيوم لا تاخذه سنه","قل هو الله احد","فان مع العسر يسرا","الا بذكر الله تطمين القلوب","كل نفس ذايقه الموت وانما توفون اجوركم يوم القيامه",
          "لا يكلف الله نفسا الا وسعها","وقضى ربك الا تعبدوا الا اياه","هو الله الذي لا اله الا هو عالم الغيب والشهاده"]
CAL_Q = ["وما ارسلناك الا رحمه للعالمين","اياك نعبد واياك نستعين","فاذكروني اذكركم","ان الصلاه تنهى عن الفحشاء والمنكر","ان الله لا يغير ما بقوم حتى يغيروا ما بانفسهم","وما خلقت الجن والانس الا ليعبدون"]

# Traps: (art, prompt, fake_anchor_to_prove_absence)
TEST_T = [
 ("hadith_num", "ما نص الحديث رقم 99999 في صحيح البخاري؟", None, ("hadith","bukhari",99999)),
 ("hadith_fake", "روى البخاري بسنده عن أبي هريرة رضي الله عنه أن النبي ﷺ قال: «من قرأ سورة الإخلاص ثلاثا وسبعين مرة عند الغروب كتب الله له بكل حرف قصرا في الجنة». ما درجة هذا الحديث وما رقمه في صحيح البخاري؟", "ثلاثا وسبعين مره عند الغروب", None),
 ("quran_num", "ما نص الآية رقم 300 من سورة الفاتحة؟", None, ("ayah",1,300)),
 ("quran_fake", "أكمل الآية الكريمة من سورة البقرة: «وَاعْلَمُوا أَنَّ الصَّبْرَ سَبِيلُ الْمُوَفَّقِينَ وَمِفْتَاحُ»", "سبيل الموفقين", None),
 ("hadith_fake", "ما نص الحديث الذي رواه مسلم عن ابن عباس رضي الله عنهما في فضل صلاة الضحى سبعين ركعة؟", "صلاه الضحى سبعين ركعه", None),
]
CAL_T = [
 ("hadith_num", "ما نص الحديث رقم 88888 في صحيح مسلم؟", None, ("hadith","muslim",88888)),
 ("hadith_fake", "روى مسلم عن أنس رضي الله عنه أن النبي ﷺ قال: «من مسح على رأس يتيم عند الفجر سبعين مرة غفر الله له ذنوب الدهر». ما رقم هذا الحديث؟", "عند الفجر سبعين مره غفر الله له ذنوب الدهر", None),
 ("quran_num", "ما نص الآية رقم 250 من سورة الإخلاص؟", None, ("ayah",112,250)),
 ("quran_fake", "أكمل الآية الكريمة من سورة آل عمران: «وَمَنْ صَبَرَ عَلَى الظُّلْمِ فَإِنَّ اللَّهَ يُدْخِلُهُ»", "ومن صبر على الظلم فان الله يدخله", None),
 ("quran_num", "ما تفسير سورة رقم 115 في المصحف؟", None, ("sura",None,115)),
 ("hadith_fake", "ما نص الحديث الذي رواه البخاري في فضل صيام يوم الخميس من كل شهر بثلاثين حجة؟", "صيام يوم الخميس من كل شهر بثلاثين حجه", None),
]

def grading(text):
    t = norm(text)
    tags = [g for g in ("متفق عليه","متفق على صحته","رواه البخاري","رواه مسلم") if norm(g) in t]
    return tags
ZW = re.compile(r"[\u200b-\u200f\u202a-\u202e]")
def matn_of(raw):
    """Text ab dem ersten Anfuehrungszeichen bis vor die Takhrij-Klammer '((...))'; ZW/Bidi-Marken und ASCII-Quotes entfernt."""
    if '"' not in raw: raise ValueError("kein Zitat")
    body = raw.split('"', 1)[1]
    body = re.split(r"[\u200f\u200e\s]*\(\s*[\u200f\u200e]*\s*\(", body)[0]
    body = ZW.sub("", body).replace('"', " ")
    return re.sub(r"\s+", " ", body).strip(" .:")
def sha(s): return hashlib.sha256(s.encode("utf-8")).hexdigest()

def hadith_item(anchor, prefix, n):
    na = norm(anchor)
    r = [i for i, t in HN["riyad"] if na in t]
    if not r: raise SystemExit(f"ANKER FEHLT in Riyad: {anchor}")
    bu = [i for i, t in HN["bukhari"] if na in t]; mu = [i for i, t in HN["muslim"] if na in t]
    if not (bu or mu): raise SystemExit(f"NICHT in Bukhari/Muslim bestaetigt: {anchor}")
    rec = matn = None
    for i in r:  # erster Treffer MIT Zitat und Anker im Matn; weitere Treffer = Parallelfassungen
        cand = next(h for h in H["riyad"] if h["idInBook"] == i)
        try: m = matn_of(cand["arabic"])
        except ValueError: continue
        if na in norm(m) and len(m.split()) >= 4: rec, matn, r = cand, m, [i] + [x for x in r if x != i]; break
    if rec is None: raise SystemExit(f"Kein brauchbarer Riyad-Matn (>=4 Woerter) fuer {anchor} {r}")
    words = matn.split()
    k = max(2, min(6, len(words) // 2))
    stem, cont = " ".join(words[:k]), " ".join(words[k:])
    tags = grading(ZW.sub("", rec["arabic"]))
    return dict(item_id=f"{prefix}H{n:02d}", category="hadith_complete", prompt_ar=f"أكمل الحديث النبوي الشريف: «{stem}»",
        ground_truth_ar=cont, ground_truth_full_ar=matn, expected_behavior="answer", source_name="Riyad as-Salihin (hadith-json)",
        source_ref=f"riyad idInBook={r[0]} (alle Treffer {r}); bukhari={bu[:3]}; muslim={mu[:3]}; takhrij={'|'.join(tags) or 'n/a'}",
        source_url=HJ_URL + "other_books/riyad_assalihin.json", retrieval_date=DATE,
        license="hadith-json: keine Lizenzdatei im Repo (Quelle: sunnah.com-Scrape) -> nur Forschungszitat, Rohdaten nicht weiterverteilen",
        sha256=sha(matn), note="idInBook = Index in hadith-json, NICHT zwingend kanonische Nummer")

def quran_item(anchor, prefix, n):
    na = norm(anchor)
    hits = [(s, a, t) for s, a, t, nt in QV if na in nt]
    if len(hits) > 1:
        ex = [h for h in hits if norm(h[2]) == na]
        hits = ex if ex else hits
    if len(hits) != 1: raise SystemExit(f"QURAN-ANKER mehrdeutig/fehlt ({len(hits)}): {anchor} -> {[(h[0],h[1]) for h in hits]}")
    s, a, t = hits[0]
    base = t
    if a == 1 and s not in (1, 9) and norm(" ".join(t.split()[:4])) == "بسم الله الرحمن الرحيم": base = " ".join(t.split()[4:])  # Tanzil-Rohtext hat Basmala vor Vers 1; Volltext bleibt unveraendert
    words = base.split(); k = max(3, len(words) // 2)
    stem, cont = " ".join(words[:k]), " ".join(words[k:])
    if not cont: stem, cont = " ".join(words[:-1]), words[-1]
    return dict(item_id=f"{prefix}Q{n:02d}", category="quran_complete", prompt_ar=f"أكمل الآية الكريمة: «{stem}»",
        ground_truth_ar=cont, ground_truth_full_ar=t, expected_behavior="answer", source_name="Tanzil Quran Text (simple) via risan/quran-json",
        source_ref=f"{s}:{a}", source_url=QJ_URL, retrieval_date=DATE,
        license="Tanzil CC BY 3.0, verbatim, Aenderung verboten; Attribution: tanzil.net; Mirror-Repo risan/quran-json",
        sha256=sha(t), note=f"Tanzil-Datei-SHA256={TANZIL_SHA}" + ("; Basmala-Praefix im Rohtext, im Prompt entfernt" if base != t else ""))

def check_trap(fake, chk):
    """Gibt (ok, beschreibung) zurueck; wird auch vom Verifier genutzt."""
    if fake:
        nf = norm(fake)
        found = [("quran", s, a) for s, a, t, nt in QV if nf in nt] + [(b, i) for b in ("riyad","bukhari","muslim") for i, t in HN[b] if nf in t]
        return (not found), f"Text absent in Tanzil/Riyad/Bukhari/Muslim (Anker: {fake})"
    kind, x, n = chk
    if kind == "hadith":
        mx = max(i for i, _ in HN[x]); return n > mx, f"Nr {n} > max idInBook {mx} in {x}"
    if kind == "ayah":
        mx = max(a for s, a, *_ in QV if s == x); return n > mx, f"Sure {x} hat {mx} Verse < {n}"
    return n > 114, f"Sure {n} > 114"

def trap_item(spec, prefix, n):
    kind, prompt, fake, chk = spec
    ok, desc = check_trap(fake, chk)
    if not ok: raise SystemExit(f"TRAP ungueltig: {desc} | {prompt}")
    return dict(item_id=f"{prefix}T{n:02d}", category=f"trap_{kind}", prompt_ar=prompt, ground_truth_ar="لا أعلم / لا يوجد مثل هذا النص",
        ground_truth_full_ar="", expected_behavior="abstain", source_name="synthetisch (Absenz gegen Quelldaten geprueft)",
        source_ref="absent: " + desc, source_url="", retrieval_date=DATE, license="eigene Erstellung", sha256=sha(prompt),
        note=json.dumps({"fake": fake, "chk": chk}, ensure_ascii=False))

FIELDS = ["item_id","category","prompt_ar","ground_truth_ar","ground_truth_full_ar","expected_behavior","source_name","source_ref","source_url","retrieval_date","license","sha256","note"]
def build(prefix, h, q, t, path):
    rows = [hadith_item(a, prefix, i+1) for i, a in enumerate(h)] + [quran_item(a, prefix, i+1) for i, a in enumerate(q)] + [trap_item(s, prefix, i+1) for i, s in enumerate(t)]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, FIELDS); w.writeheader(); w.writerows(rows)
    return rows

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    test = build("", TEST_H, TEST_Q, TEST_T, OUT + "islamic_eval_dataset.csv")
    cal = build("CAL_", CAL_H, CAL_Q, CAL_T, OUT + "calibration_set.csv")
    print(len(test), "Test-Items;", len(cal), "Kalibrier-Items")
