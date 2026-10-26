#!/usr/bin/env python3
"""
run_eval.py v2 - fuehrt Prompts gegen einen OpenAI-kompatiblen Endpunkt (vLLM) aus. Streamt (TTFT), schreibt JSONL.
Aenderungen ggue. v1: alle CSV-Spalten werden durchgereicht (der Scorer braucht variants_json/disputed), max_tokens per Flag
(Default 1536: Fara'id-Antworten mit JSON am Ende wurden bei 512 abgeschnitten), finish_reason + usage werden protokolliert,
'localhost' -> 127.0.0.1 (Windows verliert sonst ~2 s pro Verbindung durch IPv6-Fallback und verfaelscht TTFT), 1 Wiederholung bei Fehler.
"""
import argparse, csv, json, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def split_think(text):
    """Trennt <think>...</think> vom Antworttext. -> (antwort, denktext, offen) ; offen=True: <think> ohne Ende (abgeschnitten im Denken)."""
    if "</think>" in text:
        pre, post = text.rsplit("</think>", 1)
        return post.strip(), pre.replace("<think>", "").strip(), False
    if "<think>" in text:
        return "", text.split("<think>", 1)[1].strip(), True
    return text.strip(), "", False


def stream_query(api_base, model, prompt, timeout, max_tokens, system=None, retries=1, sampling=None):
    url = api_base.rstrip("/") + "/chat/completions"
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    payload = {"model": model, "messages": msgs, "temperature": 0.0, "max_tokens": max_tokens,
               "stream": True, "stream_options": {"include_usage": True}}
    payload.update(sampling or {})                      # temperature/top_p/top_k/seed ueberschreiben Greedy
    last_err = None
    for attempt in range(retries + 1):
        t0 = time.perf_counter(); ttft = ttft_c = None; chunks = []; think = []; finish = None; usage = None
        try:
            r = requests.post(url, json=payload, stream=True, timeout=timeout)
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                d = line.decode("utf-8").strip()
                if not d.startswith("data:") or d.endswith("[DONE]"):
                    continue
                c = json.loads(d[5:].strip())
                if c.get("usage"):
                    usage = c["usage"]
                ch = c.get("choices") or []          # letzter usage-Chunk hat choices == []
                if not ch:
                    continue
                dl = ch[0].get("delta") or {}
                rt = dl.get("reasoning_content") or dl.get("reasoning") or ""   # vLLM mit --reasoning-parser
                tok = dl.get("content") or ""
                now = (time.perf_counter() - t0) * 1000
                if (rt or tok) and ttft is None:
                    ttft = now                      # erstes Token irgendeiner Art
                if rt:
                    think.append(rt)
                if tok:
                    if ttft_c is None:
                        ttft_c = now                # erstes Antwort-Token (nach dem Denken)
                    chunks.append(tok)
                if ch[0].get("finish_reason"):
                    finish = ch[0]["finish_reason"]
            total = (time.perf_counter() - t0) * 1000
            ans, inline_think, open_think = split_think("".join(chunks))
            return {"status": "success", "response": ans, "reasoning": ("".join(think) or inline_think), "open_think": open_think,
                    "ttft_ms": round(ttft if ttft is not None else total, 2), "ttft_content_ms": round(ttft_c if ttft_c is not None else total, 2),
                    "total_ms": round(total, 2), "finish_reason": finish, "usage": usage, "error": None, "attempts": attempt + 1}
        except Exception as e:
            last_err = str(e)
            time.sleep(2)
    return {"status": "error", "response": "", "reasoning": "", "open_think": False, "ttft_ms": 0.0, "ttft_content_ms": 0.0, "total_ms": 0.0,
            "finish_reason": None, "usage": None, "error": last_err, "attempts": retries + 1}


def main():
    ap = argparse.ArgumentParser(description="vLLM Inferenz Runner")
    ap.add_argument("--api-base", default="http://127.0.0.1:8000/v1")
    ap.add_argument("--model-name", required=True, help="MUSS exakt dem --served-model-name des Servers entsprechen")
    ap.add_argument("--input-csv", required=True)
    ap.add_argument("--output-jsonl", required=True)
    ap.add_argument("--max-items", type=int)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--max-tokens", type=int, default=1536, help="Reasoning-Modelle brauchen deutlich mehr (Denken zaehlt mit)")
    ap.add_argument("--concurrency", type=int, default=1, help=">1 beschleunigt den Genauigkeitslauf; TTFT/Tok/s sind dann KEINE Latenzmessung")
    ap.add_argument("--system-prompt", default=None, help="optional, z. B. fuer Modelle ohne Chat-Template")
    ap.add_argument("--temperature", type=float, default=None, help="Standard: 0.0 (greedy)")
    ap.add_argument("--top-p", type=float, default=None)
    ap.add_argument("--top-k", type=int, default=None)
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args()
    samp = {k: v for k, v in (("temperature", a.temperature), ("top_p", a.top_p), ("top_k", a.top_k), ("seed", a.seed)) if v is not None}
    print(f"[*] Sampling: {samp or 'greedy (temperature 0.0)'}")
    base = a.api_base.replace("//localhost", "//127.0.0.1")
    print(f"[*] Runner: {a.model_name} @ {base} | max_tokens={a.max_tokens} | concurrency={a.concurrency}")
    items = list(csv.DictReader(open(a.input_csv, encoding="utf-8-sig")))
    if a.max_items:
        items = items[:a.max_items]; print(f"[!] DRY-RUN: {len(items)} Items")
    lock = threading.Lock(); ok = [0]; done = [0]
    out = open(a.output_jsonl, "w", encoding="utf-8")

    def work(it):
        res = stream_query(base, a.model_name, it["prompt_ar"], a.timeout, a.max_tokens, a.system_prompt, sampling=samp)
        rec = dict(it)
        rec.update({"model": a.model_name, "raw_response": res["response"], "status": res["status"], "error": res["error"],
                    "finish_reason": res["finish_reason"], "usage": res["usage"], "attempts": res["attempts"], "open_think": res["open_think"],
                    "reasoning_chars": len(res["reasoning"]), "reasoning_text": res["reasoning"][:6000], "concurrency": a.concurrency,
                    "max_tokens": a.max_tokens, "sampling": samp or {"temperature": 0.0},
                    "metrics": {"ttft_ms": res["ttft_ms"], "ttft_content_ms": res["ttft_content_ms"], "total_ms": res["total_ms"]},
                    "timestamp": datetime.now().isoformat()})
        with lock:
            done[0] += 1
            if res["status"] == "success":
                ok[0] += 1
                n = (res["usage"] or {}).get("completion_tokens")
                print(f"  [{done[0]:02d}/{len(items):02d}] {it['item_id']:<10} OK total={res['total_ms']}ms tokens={n} finish={res['finish_reason']} denken={len(res['reasoning'])}z", flush=True)
            else:
                print(f"  [{done[0]:02d}/{len(items):02d}] {it['item_id']:<10} FEHLER: {res['error']}", flush=True)
            out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush()

    with ThreadPoolExecutor(max_workers=max(1, a.concurrency)) as ex:
        list(ex.map(work, items))
    out.close()
    print(f"[+] {ok[0]}/{len(items)} erfolgreich -> {a.output_jsonl}")
    sys.exit(0 if ok[0] == len(items) else 2)


if __name__ == "__main__":
    main()
