import argparse, csv, json, os, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from openai import OpenAI

def split_think(text):
    if "</think>" in text:
        pre, post = text.rsplit("</think>", 1)
        return post.strip(), pre.replace("<think>", "").strip(), False
    if "<think>" in text:
        return "", text.split("<think>", 1)[1].strip(), True
    return text.strip(), "", False

def stream_query(client, model, prompt, timeout, max_tokens, temperature, seed, retries=2):
    for attempt in range(retries + 1):
        t0 = time.perf_counter()
        ttft, chunks, finish_reason, usage = None, [], None, None
        try:
            extra_args = {}
            if seed is not None: extra_args["seed"] = seed
            if temperature is not None: extra_args["temperature"] = temperature
            
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                stream=True,
                stream_options={"include_usage": True},
                timeout=timeout,
                **extra_args
            )
            for chunk in response:
                now = (time.perf_counter() - t0) * 1000
                if chunk.usage:
                    usage = {"prompt_tokens": chunk.usage.prompt_tokens, "completion_tokens": chunk.usage.completion_tokens, "total_tokens": chunk.usage.total_tokens}
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    tok = delta.content or ""
                    if tok:
                        if ttft is None: ttft = now
                        chunks.append(tok)
                    if chunk.choices[0].finish_reason:
                        finish_reason = chunk.choices[0].finish_reason
            total = (time.perf_counter() - t0) * 1000
            ans, inline_think, open_think = split_think("".join(chunks))
            return {"status": "success", "response": ans, "reasoning": inline_think, "open_think": open_think,
                    "ttft_ms": round(ttft if ttft is not None else total, 2), "ttft_content_ms": round(ttft if ttft is not None else total, 2),
                    "total_ms": round(total, 2), "finish_reason": finish_reason or "stop", "usage": usage, "error": None, "attempts": attempt + 1}
        except Exception as e:
            time.sleep(2)
    return {"status": "error", "response": "", "reasoning": "", "open_think": False, "ttft_ms": 0.0, "ttft_content_ms": 0.0, "total_ms": 0.0,
            "finish_reason": None, "usage": None, "error": str(e), "attempts": retries + 1}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-name", default="gpt-4o")
    ap.add_argument("--input-csv", default="faraid_eval_dataset.csv")
    ap.add_argument("--output-jsonl", default="faraid_gpt4o.jsonl")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--max-tokens", type=int, default=1536)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--timeout", type=int, default=60)
    a = ap.parse_args()

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    items = list(csv.DictReader(open(a.input_csv, encoding="utf-8-sig")))
    print(f"[*] Starte API-Lauf: {a.model_name} | {len(items)} Items")
    
    lock = threading.Lock()
    done, ok = [0], [0]
    out_f = open(a.output_jsonl, "w", encoding="utf-8")

    def work(it):
        res = stream_query(client, a.model_name, it["prompt_ar"], a.timeout, a.max_tokens, a.temperature, a.seed)
        rec = dict(it)
        rec.update({
            "model": a.model_name, "raw_response": res["response"], "status": res["status"], "error": res["error"],
            "finish_reason": res["finish_reason"], "usage": res["usage"], "attempts": res["attempts"],
            "open_think": res["open_think"], "reasoning_chars": len(res["reasoning"]), "reasoning_text": res["reasoning"][:6000],
            "concurrency": a.concurrency, "max_tokens": a.max_tokens, "sampling": {"temperature": a.temperature, "seed": a.seed},
            "metrics": {"ttft_ms": res["ttft_ms"], "ttft_content_ms": res["ttft_content_ms"], "total_ms": res["total_ms"]},
            "timestamp": datetime.now().isoformat()
        })
        with lock:
            done[0] += 1
            toks = (res["usage"] or {}).get("completion_tokens", 0)
            if res["status"] == "success":
                ok[0] += 1
                print(f"  [{done[0]:02d}/{len(items):02d}] {it['item_id']} OK | {res['total_ms']:.0f}ms | {toks} Tok", flush=True)
            else:
                print(f"  [{done[0]:02d}/{len(items):02d}] {it['item_id']} FEHLER: {res['error']}", flush=True)
            out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out_f.flush()

    with ThreadPoolExecutor(max_workers=max(1, a.concurrency)) as pool:
        list(pool.map(work, items))
    out_f.close()
    print(f"[+] Fertig: {ok[0]}/{len(items)} -> {a.output_jsonl}")

if __name__ == "__main__":
    main()
