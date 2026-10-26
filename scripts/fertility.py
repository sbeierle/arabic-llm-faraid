#!/usr/bin/env python3
"""Tokenizer-Fertilitaet (Saeule 1): Tokens pro Wort / pro 100 Zeichen auf gepinnten arabischen Korpora. Braucht KEINE GPU, nur die Tokenizer-Dateien.
  python3 scripts/fertility.py --models "qwen3-30b-a3b=Qwen/Qwen3-30B-A3B,jais3-mova=inception42/Jais-3-MoVA-36B-A4B" --out results_ext/fertility.json
  python3 scripts/fertility.py --selftest        (nur Pipeline-Test mit winzigen selbst trainierten Tokenizern - Zahlen bedeutungslos)
Korpora: Koran (Tanzil simple, 6236 Verse) mit und ohne Tashkeel; Bukhari (Zufallsstichprobe, Seed fest); 50 Fara'id-Prompts arabisch vs. englisch (parallel).
Woerter = Leerzeichen-getrennt. Unsicherheit: Bootstrap ueber Dokumente (95%), paarweise fuer das Verhaeltnis der Modelle."""
import argparse, csv, json, os, random, re, sys
import numpy as np
ROOT = os.environ.get("ARABIC_BENCH_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MARK = re.compile("[ً-ٰٟۖ-ۭـ]")
ZW = re.compile(r"[​-‏‪-‮]")
def strip_marks(s): return re.sub(r"\s+", " ", MARK.sub("", s).replace("ٱ", "ا")).strip()

def corpora():
    Q = json.load(open(ROOT + "/data/raw/quran-json/data/tanzil/simple.json", encoding="utf-8"))
    verses = [v["text"] for s in sorted(Q, key=int) for v in Q[s]]
    B = json.load(open(ROOT + "/data/raw/hadith-json/db/by_book/the_9_books/bukhari.json", encoding="utf-8"))["hadiths"]
    rnd = random.Random(20261025); idx = rnd.sample(range(len(B)), 1500)
    hadith = [re.sub(r"\s+", " ", ZW.sub("", B[i]["arabic"])).strip() for i in sorted(idx)]
    ar = list(csv.DictReader(open(ROOT + "/data/items/faraid_eval_dataset.csv", encoding="utf-8-sig")))
    en = list(csv.DictReader(open(ROOT + "/data/items/faraid_en_dataset.csv", encoding="utf-8-sig")))
    return {"quran_mit_tashkeel": verses, "quran_ohne_tashkeel": [strip_marks(v) for v in verses], "bukhari_1500": hadith,
            "faraid_prompt_ar": [r["prompt_ar"] for r in ar], "faraid_prompt_en": [r["prompt_ar"] for r in en]}

def load_tokenizer(spec, texts_for_selftest=None):
    """-> (encode_lengths(list[str]) -> list[int], info dict)"""
    if spec.startswith("selftest:"):
        from tokenizers import Tokenizer, models, trainers, pre_tokenizers
        vs = int(spec.split(":")[1]); t = Tokenizer(models.BPE(unk_token="[UNK]")); t.pre_tokenizer = pre_tokenizers.Whitespace()
        t.train_from_iterator(texts_for_selftest, trainers.BpeTrainer(vocab_size=vs, special_tokens=["[UNK]"]))
        return (lambda xs: [len(e.ids) for e in t.encode_batch(xs)]), {"repo": spec, "vocab_size": t.get_vocab_size(), "klasse": "selftest-BPE"}
    try:
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained(spec, trust_remote_code=True)
        def enc(xs):
            out = []
            for i in range(0, len(xs), 256): out += [len(x) for x in tok(xs[i:i + 256], add_special_tokens=False)["input_ids"]]
            return out
        return enc, {"repo": spec, "vocab_size": len(tok), "klasse": type(tok).__name__}
    except Exception as e:
        print(f"   [!] AutoTokenizer fuer {spec} fehlgeschlagen ({type(e).__name__}: {str(e)[:120]}) -> Fallback tokenizer.json", file=sys.stderr)
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer
        t = Tokenizer.from_file(hf_hub_download(spec, "tokenizer.json"))
        return (lambda xs: [len(e.ids) for e in t.encode_batch(xs, add_special_tokens=False)]), {"repo": spec, "vocab_size": t.get_vocab_size(), "klasse": "tokenizers-Fallback (tokenizer.json)"}

def stats(lens, texts, rnd_seed=42, nboot=1000):
    lens = np.array(lens, float); words = np.array([len(t.split()) for t in texts], float); chars = np.array([len(re.sub(r"\s", "", t)) for t in texts], float)
    def tpw(ix): return lens[ix].sum() / words[ix].sum()
    rng = np.random.RandomState(rnd_seed); n = len(texts); allix = np.arange(n)
    boots = np.array([tpw(rng.randint(0, n, n)) for _ in range(nboot)])
    return dict(docs=n, tokens=int(lens.sum()), words=int(words.sum()), chars=int(chars.sum()), tokens_per_word=float(tpw(allix)),
                tpw_ci95=[float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))], tokens_per_100chars=float(100 * lens.sum() / chars.sum()))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--models", default=""); ap.add_argument("--out", default="results_ext/fertility.json"); ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(); C = corpora(); allt = [t for v in C.values() for t in v]
    specs = {"selftest-klein": "selftest:3000", "selftest-gross": "selftest:12000"} if a.selftest else dict(kv.split("=", 1) for kv in a.models.split(",") if kv)
    if not specs: sys.exit("--models \"tag=repo,tag2=repo2\" angeben")
    res = {"korpora": {k: len(v) for k, v in C.items()}, "modelle": {}, "paarweise": {}}; L = {}
    for tag, spec in specs.items():
        print(f"[*] {tag}: lade Tokenizer {spec}"); enc, info = load_tokenizer(spec, allt)
        L[tag] = {k: enc(v) for k, v in C.items()}
        res["modelle"][tag] = {"tokenizer": info, **{k: stats(L[tag][k], C[k]) for k in C}}
        for k in C: s = res["modelle"][tag][k]; print(f"    {k:<22} {s['tokens_per_word']:.3f} Tok/Wort  (CI {s['tpw_ci95'][0]:.3f}-{s['tpw_ci95'][1]:.3f})  {s['tokens_per_100chars']:.1f} Tok/100 Zeichen")
    tags = list(specs)
    for i in range(len(tags)):
        for j in range(i + 1, len(tags)):
            A, B = tags[i], tags[j]; out = {}
            for k in C:                                         # Verhaeltnis A/B mit paarweisem Bootstrap ueber dieselben Dokumente
                la, lb = np.array(L[A][k], float), np.array(L[B][k], float); n = len(la); rng = np.random.RandomState(42)
                r = np.array([(la[ix].sum() / lb[ix].sum()) for ix in (rng.randint(0, n, n) for _ in range(1000))])
                out[k] = {"ratio": float(la.sum() / lb.sum()), "ci95": [float(np.percentile(r, 2.5)), float(np.percentile(r, 97.5))]}
            res["paarweise"][f"{A}/{B}"] = out
            print(f"[*] Verhaeltnis Tokens {A}/{B}: " + ", ".join(f"{k}={v['ratio']:.2f}" for k, v in out.items()))
    # Arabisch-vs-Englisch-Aufschlag je Modell (parallele Fara'id-Prompts)
    for tag in tags:
        la, le = np.array(L[tag]["faraid_prompt_ar"], float), np.array(L[tag]["faraid_prompt_en"], float)
        res["modelle"][tag]["ar_zu_en_tokenverhaeltnis_faraid"] = float(la.sum() / le.sum())
        print(f"[*] {tag}: Fara'id-Prompt arabisch/englisch = {la.sum() / le.sum():.2f} x Tokens (Text nicht wortgleich uebersetzt: nur grobe Orientierung)")
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True); json.dump(res, open(a.out, "w", encoding="utf-8"), indent=2, ensure_ascii=False); print("[+]", a.out)
if __name__ == "__main__": main()
