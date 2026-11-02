import json, re, sys, time, requests
BASE = "http://localhost:8000/v1"
D = "/workspace/fiqh_eval/"
SRC = D + "fiqh_questions_v2.jsonl"
NRUNS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
TEMP = float(sys.argv[2]) if len(sys.argv) > 2 else 0.7
TAGM = sys.argv[3] if len(sys.argv) > 3 else "jais"
OUT = D + "fiqh_runs_v2_%s.json" % TAGM
MAXTOK = 8000

PROMPT = """You are an expert in comparative Islamic jurisprudence (fiqh).
Question (Arabic): {q}

State the position on this question for each of the following voices, as that voice's own school/scholar would state it (the reliable/mu'tamad view of the school; mention internal disagreement only in 'note').
Voices: hanafi, maliki, shafii, hanbali (the four classical madhhabs) and ibn_baz, ibn_uthaymin (two contemporary Saudi scholars, treated separately).

Rules:
- Do not blend schools. Each voice gets its own answer.
- If you do not know a voice's position, set "ruling" to null. Do not guess.
- "source" = a specific book (and author) you are confident about, otherwise null.
- "consensus_status" = "ijma" only if there is truly no disagreement among the four schools, otherwise "khilaf".

Answer with ONLY one JSON object, no text before or after:
{{
 "hanafi": {{"ruling": "...", "source": "...", "note": "..."}},
 "maliki": {{"ruling": "...", "source": "...", "note": "..."}},
 "shafii": {{"ruling": "...", "source": "...", "note": "..."}},
 "hanbali": {{"ruling": "...", "source": "...", "note": "..."}},
 "ibn_baz": {{"ruling": "...", "source": "...", "note": "..."}},
 "ibn_uthaymin": {{"ruling": "...", "source": "...", "note": "..."}},
 "consensus_status": "ijma | khilaf"
}}"""

model = requests.get(BASE + "/models", timeout=30).json()["data"][0]["id"]
print("Modell:", model, flush=True)
rows = [json.loads(l) for l in open(SRC, encoding="utf-8") if l.strip()]
res = []
for run, i, r in [(k, n, row) for k in range(1, NRUNS + 1) for n, row in enumerate(rows, 1)]:
    t0 = time.time()
    rec = {"run": run, "temp": TEMP, "id": r["id"], "frage_ar": r["frage_ar"] if "frage_ar" in r else r.get("frage")}
    try:
        resp = requests.post(BASE + "/chat/completions", timeout=1800, json={
            "model": model, "max_tokens": MAXTOK, "temperature": TEMP,
            "messages": [{"role": "user", "content": PROMPT.format(q=rec["frage_ar"])}]})
        j = resp.json()
        if "choices" not in j:
            rec["error"] = json.dumps(j, ensure_ascii=False)[:500]
        else:
            c = j["choices"][0]; m = c["message"]
            txt = m.get("content") or ""
            rec["finish_reason"] = c.get("finish_reason")
            rec["reasoning"] = m.get("reasoning_content") or m.get("reasoning")
            rec["raw"] = txt
            if "</think>" in txt: txt = txt.split("</think>")[-1]
            mm = re.search(r"\{.*\}", txt, re.S)
            rec["parsed"] = None
            if mm:
                try: rec["parsed"] = json.loads(mm.group(0))
                except Exception as e: rec["parse_error"] = str(e)
    except Exception as e:
        rec["error"] = repr(e)
    rec["sec"] = round(time.time() - t0)
    st = "FEHLER" if "error" in rec else ("TRUNC" if rec.get("finish_reason") == "length" else ("OK" if rec.get("parsed") else "PARSE?"))
    print(f"[run {run}] [{i}/{len(rows)}] {r['id']} {st} {rec['sec']}s", flush=True)
    res.append(rec)
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("fertig ->", OUT)
