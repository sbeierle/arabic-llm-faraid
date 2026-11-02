# score_v12_auto.py  - automatische Metriken (ohne Gold): Parse/TRUNC, Null-Rate, Zitat im Kontext (Grounding)
import json, re, collections, sys
D = re.compile(r"[ـً-ٰٟ]")
def n(s): return re.sub(r"\s+", " ", re.sub("[أإآٱ]", "ا", D.sub("", s or "")).replace("ى", "ي")).strip()
P = {r["test_id"]: r for r in (json.loads(l) for l in open("fiqh_v12_rag_prompts.jsonl", encoding="utf-8"))}
R = [x for x in json.load(open(sys.argv[1] if len(sys.argv) > 1 else "fiqh_v12_results.json", encoding="utf-8")) if x["suite"] == "RAG"]
VO = ["hanafi", "maliki", "shafii", "hanbali", "ibn_baz", "ibn_uthaymin"]
agg = collections.defaultdict(lambda: collections.Counter())
for x in R:
    c = x["condition"]; a = agg[c]; a["calls"] += 1
    # finish=length = am Token-Limit abgebrochen: JSON stammt dann aus dem Denkblock -> ungueltig
    st = "TRUNC" if x.get("finish") == "length" else x["status"]
    a[st] += 1
    if st != "OK" or not x.get("parsed"): continue
    ctx = n(P[x["test_id"]]["context_ar"])
    for v in VO:
        o = x["parsed"].get(v)
        if not isinstance(o, dict): a["voice_missing"] += 1; continue
        rl = o.get("ruling"); q = o.get("evidence_quote_ar")
        if rl in (None, "", "null") or str(rl).strip().lower() == "null": a["voice_null"] += 1; continue
        a["voice_answered"] += 1
        if c != "NO_CTX":
            if q and n(q) and n(q) in ctx: a["answered_quote_grounded"] += 1
            elif q: a["answered_quote_NOT_in_ctx"] += 1
            else: a["answered_no_quote"] += 1
for c in ["NO_CTX", "ORACLE", "RET_TOP3", "WRONG"]:
    print(c, dict(agg[c]))
print("\nLesehilfe: WRONG -> 'answered' sollte ~0 sein (Kontext enthaelt die Antwort nicht); 'quote_NOT_in_ctx' = Antwort aus Parametergedaechtnis bzw. erfundenes Zitat.")
