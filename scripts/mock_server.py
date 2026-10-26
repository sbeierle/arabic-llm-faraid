#!/usr/bin/env python3
"""
mock_server.py v2 - ORAKEL-Attrappe: kennt die Items und antwortet pro Item nach festem Muster (Index i % 5 je CSV):
  0 perfekt | 1 plausibel falsch | 2 verweigert | 3 richtig, aber 'verrauscht' (ohne Tashkeel / arabisch-indische Ziffern / andere Regelvariante)
  4 Muellantwort ohne JSON bzw. Konfabulation
Damit kann test_pipeline.py die erwarteten Urteile des Scorers EXAKT vorhersagen und jede Zweigstelle des Scorers pruefen.
"""
import argparse, csv, json, os, re, sys, time
from fractions import Fraction
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ITEMS = {}
_TASH = re.compile(r"[ً-ٰٟۖ-ۭـ]")
_IND = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def load(paths):
    for p in paths:
        for i, row in enumerate(csv.DictReader(open(p, encoding="utf-8-sig"))):
            ITEMS[row["prompt_ar"]] = (i, row)


def js(d, indic=False):
    s = json.dumps(d, ensure_ascii=False)
    return s.translate(_IND) if indic else s


def reply(i, row):
    c, beh = i % 5, row["expected_behavior"]
    if beh == "answer":
        gt = row["ground_truth_ar"]
        if c == 0: return "تتمة النص: " + gt
        if c == 1:
            w = gt.split(); return " ".join(w[::-1]) if len(w) > 1 else "كلمة خاطئة"
        if c == 2: return "لا أعلم هذا النص."
        if c == 3: return "الحديث بتمامه: " + _TASH.sub("", gt)
        return "هذا نص مروي ومثبت في الأصول برواية معتمدة."
    if beh == "abstain":
        if c in (0, 2): return "لا أعلم، ولا أصل لهذا النص."
        if c == 3: return "لَا أَعْلَمُ هَذَا النَّصَّ"
        return "رواه البخاري في صحيحه برقم 1234 عن أبي هريرة، وهو حديث صحيح."
    if beh == "fraction_match":
        gold = json.loads(row["ground_truth_ar"]); variants = json.loads(row.get("variants_json") or "{}")
        if c == 0: return "الحل بالتفصيل:\n" + js(gold)
        if c == 1:
            bad = dict(gold); k = sorted(bad)[0]
            for d in (Fraction(1, 7), Fraction(1, 11), Fraction(1, 13)):
                bad[k] = str(Fraction(gold[k]) + d)
                if all(bad != v for v in variants.values()) and bad != gold: break
            return js(bad)
        if c == 2: return "لا أعلم الجواب."
        if c == 3:
            alt = [v for v in variants.values() if v != gold]
            return "النتيجة: " + js(alt[0] if (variants and alt) else gold, indic=True)
        return "للأب السدس وللبنات الثلثان ويحجب الإخوة."
    return "لا أعلم."


LAST = {}


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/last_body":
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(json.dumps(LAST).encode()); return
        self.send_response(200 if self.path == "/health" else 404); self.end_headers()
        if self.path == "/health": self.wfile.write(b'{"status":"ok"}')

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8")); LAST.clear(); LAST.update(body)
        prompt = body["messages"][-1]["content"]
        i, row = ITEMS.get(prompt, (0, None))
        text = reply(i, row) if row else "لا أعلم."
        mode = body.get("model", "")
        usage = {"prompt_tokens": 40, "completion_tokens": max(1, len(text) // 3), "total_tokens": 40 + max(1, len(text) // 3)}
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        w = lambda o: (self.wfile.write(("data: " + json.dumps(o, ensure_ascii=False) + "\n\n").encode("utf-8")), self.wfile.flush())
        time.sleep(0.03)
        if mode == "think-field":      # --reasoning-parser aktiv: Denken in reasoning_content
            w({"choices": [{"delta": {"reasoning_content": "ich ueberlege ... "}, "index": 0}]}); time.sleep(0.05)
        if mode == "think-trunc":      # Denken laeuft ins Token-Limit, nie eine Antwort
            w({"choices": [{"delta": {"reasoning_content": "ich ueberlege endlos ... "}, "index": 0}]})
            w({"choices": [{"delta": {}, "index": 0, "finish_reason": "length"}]}); w({"choices": [], "usage": usage})
            self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush(); return
        if mode == "think-inline":     # kein Parser: <think> steht im Content
            text = "<think>ich ueberlege ...</think>\n" + text
        if mode == "think-open":       # <think> ohne Ende
            text = "<think>ich ueberlege und ueberlege " 
        w({"choices": [{"delta": {"content": text[:12]}, "index": 0}]})
        time.sleep(0.05)
        w({"choices": [{"delta": {"content": text[12:]}, "index": 0}]})
        w({"choices": [{"delta": {}, "index": 0, "finish_reason": "length" if mode == "think-open" else "stop"}]})
        w({"choices": [], "usage": usage})
        self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()

    def log_message(self, *a): pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--items", nargs="+", required=True); ap.add_argument("--port", type=int, default=18000)
    a, unknown = ap.parse_known_args(); load(a.items)
    if "--reasoning-parser" in unknown and os.environ.get("MOCK_REJECT_PARSER"):
        print("error: argument --reasoning-parser: invalid choice", file=sys.stderr); sys.exit(2)
    print(f"[*] Orakel-Attrappe auf http://127.0.0.1:{a.port} ({len(ITEMS)} Items)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()
