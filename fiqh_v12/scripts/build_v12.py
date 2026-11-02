# build_v12.py  -  baut fiqh_v12_rag_prompts.jsonl + fiqh_v12_usul_prompts.jsonl
# Aufruf:  python build_v12.py  (liest fiqh_raw_sources.json, fiqh_raw_gaps.json, fiqh_pilot_gold.jsonl im selben Ordner)
import json, re, math, hashlib, collections, sys
SRC, GAPS, GOLD = "fiqh_raw_sources.json", "fiqh_raw_gaps.json", "fiqh_pilot_gold.jsonl"
TARGETS = ["FIQH_%03d" % i for i in range(1, 11)]       # alle 10 Fragen (keine Auswahl nach Fehlern)
MAXCH, K = 1200, 3

DIAC = re.compile(r"[ـً-ٰٟ]")
def norm(s):
    s = DIAC.sub("", s)
    s = re.sub("[أإآٱ]", "ا", s).replace("ى", "ي").replace("ة", "ه")
    return s
def toks(s):
    out = []
    for w in re.findall(r"[ء-ي0-9]+", norm(s)):
        for p in ("وال", "بال", "كال", "فال", "لل", "ال"):
            if w.startswith(p) and len(w) > len(p) + 2:
                w = w[len(p):]; break
        out.append(w)
    return out

STARTS = ["مسار الصفحة الحالية:", "السؤال"]
ENDS = ["مواد ذات صلة", "جميع الحقوق محفوظة", "الخدمات العلمية", "تحميل الصفحة التالية", "التالي \n السابق"]
def clean(t):
    for m in ["مسار الصفحة الحالية:"]:
        if m in t: t = t[t.find(m):]
    for e in ENDS:
        if e in t: t = t[:t.find(e)]
    return re.sub(r"\n{3,}", "\n\n", t).strip()

def passages(text):
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    out, cur = [], ""
    for p in paras:
        while len(p) > MAXCH:              # lange Absaetze hart teilen
            if cur: out.append(cur); cur = ""
            out.append(p[:MAXCH]); p = p[MAXCH:]
        if len(cur) + len(p) + 1 > MAXCH:
            out.append(cur); cur = p
        else:
            cur = (cur + "\n" + p) if cur else p
    if cur: out.append(cur)
    return [o for o in out if len(o) > 120]

# ---- Korpus
pool, seen_page = [], set()
for fn in (SRC, GAPS):
    for e in json.load(open(fn, encoding="utf-8")):
        for p in e.get("pages", []):
            t = p.get("text", "")
            if len(t) < 200: continue
            h = hashlib.md5(norm(t)[:400].encode()).hexdigest()
            key = (e["id"], h)
            if key in seen_page: continue
            seen_page.add(key)
            for ps in passages(clean(t)):
                pool.append({"qid": e["id"], "source": e.get("source"), "url": p.get("url", ""), "text": ps})
# Passagen, die identisch unter mehreren IDs vorkommen (z.B. Shamela-Deckblatt), werden zu "shared" und nie als Gold gezaehlt
cnt = collections.defaultdict(set)
for x in pool: cnt[hashlib.md5(norm(x["text"]).encode()).hexdigest()].add(x["qid"])
dedup, seen = [], set()
for x in pool:
    h = hashlib.md5(norm(x["text"]).encode()).hexdigest()
    x["shared"] = len(cnt[h]) > 1
    x["qids"] = sorted(cnt[h])
    if h in seen: continue
    seen.add(h); dedup.append(x)
pool = dedup
# Shamela-Deckblatt / Navigationsmuell raus
pool = [x for x in pool if not (x["shared"] and len(x["qids"]) > 3)]
for i, x in enumerate(pool): x["pid"] = "P%03d" % i
print("Korpus-Passagen:", len(pool), "| Seiten-IDs:", len({x['url'] for x in pool}))

# ---- BM25
class BM25:
    def __init__(s, docs, k1=1.5, b=0.75):
        s.tf = [collections.Counter(toks(d)) for d in docs]; s.len = [sum(t.values()) for t in s.tf]
        s.avg = sum(s.len) / len(docs); s.k1, s.b = k1, b
        df = collections.Counter(w for t in s.tf for w in t); N = len(docs)
        s.idf = {w: math.log(1 + (N - n + .5) / (n + .5)) for w, n in df.items()}
    def score(s, q, i):
        t = s.tf[i]; sc = 0
        for w in set(toks(q)):
            if w in t:
                f = t[w]; sc += s.idf[w] * f * (s.k1 + 1) / (f + s.k1 * (1 - s.b + s.b * s.len[i] / s.avg))
        return sc
bm = BM25([x["text"] for x in pool])

gold = {r["id"]: r for r in (json.loads(l) for l in open(GOLD, encoding="utf-8") if l.strip())}
def rank(q, idxs): return sorted(idxs, key=lambda i: -bm.score(q, i))

SYS_CTX = """أنت مدقق فقهي مقارن. اعتمد حصرياً على المستندات المرفقة للإجابة عن السؤال.
إذا لم تجد حكم مذهب أو عالم معين صراحة في المستندات المرفقة، ضع القيمة null في حقل ruling ولا تكمل من ذاكرتك.
أجب بصيغة JSON فقط بعد انتهاء التفكير، بهذا الهيكل:
{"consensus_status": "ijma | khilaf | null",
 "hanafi": {"ruling": "... أو null", "evidence_quote_ar": "اقتباس حرفي قصير من المستند أو null"},
 "maliki": {"ruling": "... أو null", "evidence_quote_ar": "..."},
 "shafii": {"ruling": "... أو null", "evidence_quote_ar": "..."},
 "hanbali": {"ruling": "... أو null", "evidence_quote_ar": "..."},
 "ibn_baz": {"ruling": "... أو null", "evidence_quote_ar": "..."},
 "ibn_uthaymin": {"ruling": "... أو null", "evidence_quote_ar": "..."}}"""
SYS_NOCTX = """أنت مدقق فقهي مقارن. أجب عن السؤال من معرفتك. إذا لم تعرف حكم مذهب أو عالم معين فضع القيمة null في حقل ruling.
أجب بصيغة JSON فقط بعد انتهاء التفكير، بهذا الهيكل:
{"consensus_status": "ijma | khilaf | null",
 "hanafi": {"ruling": "... أو null", "evidence_quote_ar": null},
 "maliki": {"ruling": "... أو null", "evidence_quote_ar": null},
 "shafii": {"ruling": "... أو null", "evidence_quote_ar": null},
 "hanbali": {"ruling": "... أو null", "evidence_quote_ar": null},
 "ibn_baz": {"ruling": "... أو null", "evidence_quote_ar": null},
 "ibn_uthaymin": {"ruling": "... أو null", "evidence_quote_ar": null}}"""

rows, stats = [], []
for q in TARGETS:
    g = gold[q]; fq = g["frage_ar"]
    own = [i for i, x in enumerate(pool) if q in x["qids"]]
    own_urls = {pool[i]["url"] for i in own}
    # ORACLE: bestes Passagen je Quellfamilie (Mawsua / Ibn Baz / Ibn Uthaymin) aus den EIGENEN Seiten
    orc = []
    for fam in ("kuwait_mawsua", "ibn_baz", "ibn_uthaymin"):
        c = rank(fq, [i for i in own if pool[i]["source"] == fam])
        if c: orc.append(c[0])
    # RET_TOP3: BM25 ueber den ganzen Korpus
    ret = rank(fq, range(len(pool)))[:K]
    # WRONG: nur Passagen anderer Fragen, die nicht dieselbe Seite wie eine eigene sind
    wrong = rank(fq, [i for i, x in enumerate(pool) if q not in x["qids"] and x["url"] not in own_urls])[:K]
    conds = {"NO_CTX": [], "ORACLE": orc, "RET_TOP3": ret, "WRONG": wrong}
    for c, idxs in conds.items():
        ctx = "\n\n---\n\n".join("[مستند %d | %s]\n%s" % (n, pool[i]["url"], pool[i]["text"]) for n, i in enumerate(idxs, 1))
        rows.append({"test_id": "%s_%s" % (q, c), "base_id": q, "condition": c, "thema": g["thema"], "frage_ar": fq,
                     "sys": SYS_NOCTX if c == "NO_CTX" else SYS_CTX,
                     "context_ar": ctx, "pids": [pool[i]["pid"] for i in idxs],
                     "ctx_qids": [pool[i]["qids"] for i in idxs], "ctx_chars": len(ctx)})
    hit = [q in pool[i]["qids"] for i in ret]
    stats.append((q, len(own), "".join("G" if h else "-" for h in hit), sum(len(pool[i]['text']) for i in orc), sum(len(pool[i]['text']) for i in ret)))
json.dump(pool, open("fiqh_v12_corpus.json", "w", encoding="utf-8"), ensure_ascii=False)
with open("fiqh_v12_rag_prompts.jsonl", "w", encoding="utf-8") as f:
    for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
print("RAG-Prompts:", len(rows))
print("Frage | eigene Passagen | RET_TOP3 trifft eigene Seite (G=ja) | Zeichen ORACLE | Zeichen RET")
for s in stats: print(*s, sep=" | ")
print("Recall@3 (mind. 1 eigene Passage):", sum("G" in s[2] for s in stats), "/", len(stats))

# ---- USUL: 7 Faelle, Kriterien als Checkliste; text_supported=True nur wenn im Chunk belegt
def find_chunk(url_sub, start, end):
    for fn in (SRC, GAPS):
        for e in json.load(open(fn, encoding="utf-8")):
            for p in e.get("pages", []):
                if url_sub in p.get("url", ""):
                    t = p["text"]; s = t.find(start)
                    if s != -1:
                        en = t.find(end, s) if end else len(t)
                        return t[s:en].strip(), p["url"]
    return "", ""
U = json.load(open("usul_spec.json", encoding="utf-8"))
urows = []
for sp in U:
    ch, url = find_chunk(sp["url_substr"], sp["start"], sp["end"])
    assert ch, sp["id"]
    for mode in ("CLOSED_BOOK", "OPEN_BOOK"):
        urows.append({"test_id": "%s_%s" % (sp["id"], mode), "usul_id": sp["id"], "mode": mode, "work": sp["work"], "source_url": url,
                      "question_ar": sp["question_ar"], "context_ar": ch if mode == "OPEN_BOOK" else None,
                      "criteria_de": sp["criteria_de"], "chunk_chars": len(ch)})
with open("fiqh_v12_usul_prompts.jsonl", "w", encoding="utf-8") as f:
    for r in urows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
print("USUL-Prompts:", len(urows), "| Chunk-Zeichen:", [r["chunk_chars"] for r in urows[1::2]])
