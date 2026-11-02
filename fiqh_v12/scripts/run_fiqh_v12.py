# run_fiqh_v12.py   Aufruf:  python run_fiqh_v12.py RUNS TEMP WORKERS [suite]
#   z.B.  nohup python run_fiqh_v12.py 3 0.7 4 > run_v12.log 2>&1 &
#   WORKERS 4, suite rag|usul|all (Standard all), 5. Argument = Modellkennung (jais|qwen) -> fiqh_v12_results_<kennung>.json
#   suite = rag | usul | all (Standard all).  Setzt nach Abbruch automatisch fort (ueberspringt fertige test_id+run).
import json, re, sys, time, os, threading, urllib.request
from concurrent.futures import ThreadPoolExecutor
API = "http://localhost:8000/v1"
D = "/workspace/fiqh_eval"
RAG_IN, USUL_IN = D+"/fiqh_v12_rag_prompts.jsonl", D+"/fiqh_v12_usul_prompts.jsonl"
RUNS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
TEMP = float(sys.argv[2]) if len(sys.argv) > 2 else 0.7
WORKERS = int(sys.argv[3]) if len(sys.argv) > 3 else 4
SUITE = sys.argv[4] if len(sys.argv) > 4 else "all"
MAXTOK = 7000
TAGM = sys.argv[5] if len(sys.argv) > 5 else "jais"   # Modell-Kennung fuer die Ausgabedatei
OUT = D + "/fiqh_v12_results_%s.json" % TAGM
TAG = re.compile(r"</[^<>\n]{0,20}think[^<>\n]{0,20}>", re.I)
dec = json.JSONDecoder(); lock = threading.Lock()

SYS_USUL = """أنت باحث متخصص في أصول الفقه والفقه المقارن. أجب عن السؤال بدقة، ثم أخرج النتيجة بصيغة JSON فقط بعد انتهاء التفكير بهذا الهيكل:
{"usul_principle": "القاعدة الأصولية أو وجه الاستدلال المحوري",
 "points": ["النقطة الأولى", "النقطة الثانية", "..."],
 "rebuttal_or_harmonization": "كيف ردّ أو جمع بين النصوص",
 "evidence_quote_ar": "اقتباس حرفي قصير من النص المرفق إن وُجد، وإلا null"}"""

def model():
    with urllib.request.urlopen(API+"/models", timeout=30) as r: return json.loads(r.read())["data"][0]["id"]

def extract(txt, key):
    tags = TAG.findall(txt or ""); post = TAG.split(txt)[-1] if tags else (txt or "")
    for scope, how in ((post, "nach_tag"), (txt or "", "gesamt")):
        for s in reversed([m.start() for m in re.finditer(r"\{", scope)]):
            if '"%s"' % key not in scope[s:s+800]: continue
            try:
                o, _ = dec.raw_decode(scope[s:])
                if isinstance(o, dict) and key in o: return o, how
            except Exception: pass
    return None, None

def call(m, sysm, user):
    body = {"model": m, "messages": [{"role": "system", "content": sysm}, {"role": "user", "content": user}],
            "temperature": TEMP, "max_tokens": MAXTOK}
    req = urllib.request.Request(API+"/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=600) as r: b = json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"err": e.read().decode()[:500], "sec": round(time.time()-t0, 1)}
    c = b["choices"][0]; u = b.get("usage", {})
    return {"raw": c["message"]["content"], "finish": c.get("finish_reason"), "sec": round(time.time()-t0, 1),
            "ptok": u.get("prompt_tokens"), "ctok": u.get("completion_tokens")}

def jobs():
    J = []
    if SUITE in ("rag", "all"):
        for r in (json.loads(l) for l in open(RAG_IN, encoding="utf-8") if l.strip()):
            u = ("المستندات المرجعية:\n%s\n\nالسؤال الفقهي:\n%s" % (r["context_ar"], r["frage_ar"])) if r["condition"] != "NO_CTX" else ("السؤال الفقهي:\n%s" % r["frage_ar"])
            J.append(("RAG", r["test_id"], r["sys"], u, "hanafi", {"base_id": r["base_id"], "condition": r["condition"]}))
    if SUITE in ("usul", "all"):
        for r in (json.loads(l) for l in open(USUL_IN, encoding="utf-8") if l.strip()):
            u = ("النص المرجعي (%s):\n%s\n\nالسؤال:\n%s" % (r["work"], r["context_ar"], r["question_ar"])) if r["mode"] == "OPEN_BOOK" else ("السؤال (%s):\n%s" % (r["work"], r["question_ar"]))
            J.append(("USUL", r["test_id"], SYS_USUL, u, "usul_principle", {"usul_id": r["usul_id"], "mode": r["mode"]}))
    return J

def main():
    m = model(); res = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else []
    done = {(x["test_id"], x["run"]) for x in res}
    todo = [(run, j) for run in range(1, RUNS+1) for j in jobs() if (j[1], run) not in done]
    print("Modell:", m, "| T=%s | workers=%d | offen: %d Calls" % (TEMP, WORKERS, len(todo)), flush=True)
    t_start = time.time(); n = [0]
    def work(item):
        run, (suite, tid, sysm, user, key, meta) = item
        o = call(m, sysm, user)
        if "raw" in o:
            p, how = extract(o["raw"], key)
            st = "OK" if p else ("TRUNC" if o["finish"] == "length" else "PARSE?")
        else: p, how, st = None, None, "ERR"
        rec = {"suite": suite, "run": run, "test_id": tid, "temp": TEMP, "status": st, "parsed": p, "parse_how": how, **meta, **o}
        with lock:
            res.append(rec); n[0] += 1
            json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
            print("[%d/%d] run%d %s %s %ss ptok=%s ctok=%s" % (n[0], len(todo), run, tid, st, o.get("sec"), o.get("ptok"), o.get("ctok")), flush=True)
    with ThreadPoolExecutor(WORKERS) as ex: list(ex.map(work, todo))
    dt = time.time()-t_start; ct = sum(x.get("ctok") or 0 for x in res if x.get("temp") == TEMP)
    print("Fertig. Wandzeit %.0fs | Completion-Tokens gesamt %d | ~%.1f tok/s aggregiert -> %s" % (dt, ct, ct/dt if dt else 0, OUT), flush=True)
main()
