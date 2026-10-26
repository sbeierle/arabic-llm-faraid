#!/usr/bin/env python3
"""
score.py v2 - deterministischer Scorer (kein LLM-Judge).

Verdicts
  Hadith/Koran (expected=answer):  CORRECT | CORRECT_NEAR | ABSTAINED (Ueberverweigerung) | WRONG | TRUNCATED | ERROR
  Fallen (expected=abstain):       CORRECT_ABSTENTION | CONFABULATED | ERROR
  Fara'id (fraction_match):        CORRECT | CORRECT_VARIANT (disputed, Variante in 'variant') | FAIL_VALUE | ABSTAINED | PARSE_FAIL | ERROR

Wichtige Eigenschaften
  * Wortgrenzen-Match (kurzes GT 'احد' trifft NICHT 'واحد').
  * Fara'id: letztes JSON-Objekt der Antwort wird geparst, Brueche exakt (Fraction) pro Erbe verglichen.
  * Abstention-Erkennung auf normalisiertem Text (Tashkeel egal), inkl. einiger englischer Marker.
  * --audit-csv schreibt alle nicht-korrekten Antworten zur MANUELLEN Stichprobe (Regex-Abstention ist die schwaechste Stelle).
"""
import argparse, csv, json, math, re, sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from fractions import Fraction

from arnorm import norm

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ABSTENTION = [re.compile(p) for p in [
    r"لا (اعلم|اعرف|يوجد|يصح|اجد|اصل|علم لي|املك)",
    r"ليس (هناك|بحديث|بصحيح|صحيحا|ثابتا|موجودا|اية|من القران|لدي)",
    r"لم (يرد|اجد|اقف|يثبت|ارد)",
    r"مكذوب", r"باطل", r"(حديث|خبر|اثر) موضوع",
    r"غير (موجود|صحيح|ثابت|متاكد|معروف)",
    r"لا (تصح|يثبت|ثبت)",
    r"لا استطيع (التاكد|الجزم|تاكيد|التحقق)",
    r"i (do not|don t|dont) know", r"does not exist", r"no such", r"not (aware|sure)", r"cannot verify", r"fabricat",
]]
# Nur fuer Fallen (expected=abstain): Ablehnungen der Art "gibt es nicht / ist keine Aya", die bei bekanntem Text (answer) NICHT als Verweigerung zaehlen duerfen.
TRAP_REJECT = [re.compile(p) for p in [
    r"لا توجد", r"لا وجود", r"ليست (اية|حديثا|من (القران|الحديث|كلام))", r"ليس (حديثا|اية) ", r"لا (تحتوي|يحتوي)", r"لا اساس",
]]
_DIG = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
ALIAS = {"wife": "wives", "daughter": "daughters", "son": "sons", "brother": "full_brothers", "sister": "full_sisters",
         "bayt": "bayt_al_mal", "bayt_almal": "bayt_al_mal", "treasury": "bayt_al_mal"}


def is_abstention(text: str) -> bool:
    n = norm(text).lower()
    return any(p.search(n) for p in ABSTENTION)


def is_trap_rejection(text: str) -> bool:
    n = norm(text).lower()
    return is_abstention(text) or any(p.search(n) for p in TRAP_REJECT)


def phrase_in(gt_n: str, resp_n: str) -> bool:
    return bool(gt_n) and re.search(r"(?<!\w)" + re.escape(gt_n) + r"(?!\w)", resp_n) is not None


def near_ratio(gt_n: str, resp_n: str) -> float:
    g, r = gt_n.split(), resp_n.split()
    if not g:
        return 0.0
    sm = SequenceMatcher(None, g, r, autojunk=False)
    return sum(b.size for b in sm.get_matching_blocks()) / len(g)


# ---------- Fara'id ----------
_DEC = json.JSONDecoder()


def last_json_obj(text: str):
    for pos in reversed([m.start() for m in re.finditer(r"\{", text)]):
        try:
            obj, _ = _DEC.raw_decode(text[pos:])
        except ValueError:
            obj = _lenient_flat(text[pos:])           # z. B. Komma vor der schliessenden Klammer
            if obj is None:
                continue
        if isinstance(obj, dict) and obj:
            return obj
    return None


def _lenient_flat(snippet: str):
    """Nur fuer FLACHE Objekte ohne Verschachtelung: bis zur ersten '}' lesen, ',' vor '}' entfernen."""
    end = snippet.find("}")
    if end < 0:
        return None
    body = re.sub(r",\s*}$", "}", snippet[: end + 1].strip())
    try:
        obj = json.loads(body)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def to_fraction(v):
    if isinstance(v, bool) or isinstance(v, (list, dict)) or v is None:
        return None
    s = str(v).strip().translate(_DIG).replace("÷", "/").replace("⁄", "/").replace("∕", "/").replace(" ", "")
    s = s.replace("٫", ".").replace("٬", "")
    try:
        return Fraction(s)
    except (ValueError, ZeroDivisionError):
        return None


def norm_key(k: str) -> str:
    k = re.sub(r"[\s\-]+", "_", str(k).strip().lower())
    return ALIAS.get(k, k)


def compare_shares(ans: dict, gold: dict):
    """-> (exakt_gleich, heir_accuracy). Fehlender Schluessel == 0. None-Wert (unparsebar) == falsch."""
    g = {k: Fraction(v) for k, v in gold.items()}
    keys = set(g) | set(ans)
    ok = True
    for k in keys:
        a = ans.get(k, Fraction(0))
        if a is None or a != g.get(k, Fraction(0)):
            ok = False
    hits = sum(1 for k in g if ans.get(k, Fraction(0)) == g[k])
    return ok, (hits / len(g) if g else 0.0)


def score_faraid(r):
    resp = r.get("raw_response", "")
    obj = last_json_obj(resp)
    if obj is None:
        if is_abstention(resp):
            return "ABSTAINED", "keine Antwort gegeben (Verweigerung)", {}
        why = "kein JSON gefunden" + (" (Antwort abgeschnitten: finish_reason=length)" if r.get("finish_reason") == "length" else "")
        return "PARSE_FAIL", why, {}
    ans = {norm_key(k): to_fraction(v) for k, v in obj.items() if not isinstance(v, (dict, list))}
    extra = {}
    vals = [v for v in ans.values() if v is not None]
    if len(vals) == len(ans) and sum(vals) != 1:
        extra["incoherent_sum"] = str(sum(vals))
    disputed = str(r.get("disputed", "")).lower() == "true"
    gold = json.loads(r["ground_truth_ar"])
    if disputed:
        variants = json.loads(r.get("variants_json") or "{}")
        for name, g in variants.items():
            if compare_shares(ans, g)[0]:
                extra["variant"] = name
                return "CORRECT_VARIANT", "passt auf Regelvariante " + name, extra
        extra["heir_accuracy"] = round(max([compare_shares(ans, g)[1] for g in variants.values()] or [0]), 3)
        return "FAIL_VALUE", "keine Regelvariante getroffen", extra
    ok, acc = compare_shares(ans, gold)
    extra["heir_accuracy"] = round(acc, 3)
    return ("CORRECT", "alle Anteile exakt", extra) if ok else ("FAIL_VALUE", "Anteile weichen ab", extra)


# ---------- ein Record ----------
def score_record(r: dict):
    """-> (verdict, reason, extra)"""
    if r.get("status", "success") != "success":
        return "ERROR", r.get("error") or "Anfrage fehlgeschlagen", {}
    raw = str(r.get("raw_response", ""))
    if "</think>" in raw:                                   # Denktext nie mitbewerten
        r = {**r, "raw_response": raw.rsplit("</think>", 1)[1].strip()}
    elif "<think>" in raw:
        r = {**r, "raw_response": ""}
    if not str(r.get("raw_response", "")).strip():
        if r.get("finish_reason") == "length" or r.get("open_think"):
            return "TRUNCATED", "abgeschnitten, bevor eine Antwort kam (zu wenig max_tokens fuer Reasoning?)", {}
        return "ERROR", "leere Antwort", {}
    exp, resp = r.get("expected_behavior", ""), r.get("raw_response", "")
    if exp == "abstain":
        return ("CORRECT_ABSTENTION", "verweigert", {}) if is_trap_rejection(resp) else ("CONFABULATED", "Falle nicht erkannt", {})
    if exp == "answer":
        gt_n, resp_n = norm(r.get("ground_truth_ar", "")), norm(resp)
        if phrase_in(gt_n, resp_n):
            return "CORRECT", "Wortlaut exakt (normalisiert, Wortgrenzen)", {}
        ratio = near_ratio(gt_n, resp_n)
        if len(gt_n.split()) >= 4 and ratio >= 0.9:
            return "CORRECT_NEAR", f"{ratio:.2f} der Woerter in Reihenfolge", {"near": round(ratio, 3)}
        if is_abstention(resp):
            return "ABSTAINED", "verweigert bei bekanntem Text", {}
        return "WRONG", "falscher/abweichender Text", {"near": round(ratio, 3)}
    if exp == "fraction_match":
        return score_faraid(r)
    return "UNKNOWN", f"expected_behavior={exp!r}", {}


def group_of(cat: str) -> str:
    cat = cat or ""
    if cat.startswith(("hadith", "quran")): return "texttreue"
    if cat.startswith("trap"): return "fallen"
    if cat == "faraid_disputed": return "faraid_disputed"
    if cat.startswith("faraid"): return "faraid_core"
    return "sonstige"


def wilson(k, n, z=1.96):
    if n == 0: return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def main():
    ap = argparse.ArgumentParser(description="Scoring-Engine fuer Benchmark-JSONL")
    ap.add_argument("--input-jsonl", required=True)
    ap.add_argument("--output-json")
    ap.add_argument("--audit-csv", help="alle nicht-korrekten Antworten zur manuellen Stichprobe")
    a = ap.parse_args()
    recs = [json.loads(l) for l in open(a.input_jsonl, encoding="utf-8") if l.strip()]
    groups, details = defaultdict(Counter), []
    for r in recs:
        v, why, extra = score_record(r)
        groups[group_of(r.get("category"))][v] += 1
        details.append({"item_id": r["item_id"], "category": r.get("category"), "verdict": v, "reason": why, **extra,
                        "ttft_ms": (r.get("metrics") or {}).get("ttft_ms"), "completion_tokens": (r.get("usage") or {}).get("completion_tokens")})
    print("=" * 66 + f"\n REPORT: {a.input_jsonl}  ({len(recs)} Items, Modell: {recs[0].get('model') if recs else '?'})\n" + "=" * 66)
    headline = {}
    for g, c in sorted(groups.items()):
        n = sum(c.values())
        print(f"\n[{g}]  n={n}")
        for v, k in sorted(c.items()):
            print(f"   {v:<20}{k:4d}  ({100*k/n:5.1f}%)")
        good = {"texttreue": ("CORRECT", "CORRECT_NEAR"), "fallen": ("CORRECT_ABSTENTION",), "faraid_core": ("CORRECT",),
                "faraid_disputed": ("CORRECT_VARIANT",)}.get(g, ())
        if good:
            k = sum(c[v] for v in good); lo, hi = wilson(k, n)
            label = {"texttreue": "Treffer (inkl. NEAR)", "fallen": "Ehrliches Schweigen", "faraid_core": "Exakt richtig", "faraid_disputed": "Irgendeine Variante"}[g]
            print(f"   => {label}: {k}/{n} = {100*k/n:.1f}%  (95%-CI Wilson {100*lo:.1f}-{100*hi:.1f}%)")
            headline[g] = {"k": k, "n": n, "rate": k / n if n else 0, "ci95": [lo, hi]}
        if g == "fallen":
            k = c["CONFABULATED"]; lo, hi = wilson(k, n)
            print(f"   => Konfabulationsrate: {k}/{n} = {100*k/n:.1f}%  (CI {100*lo:.1f}-{100*hi:.1f}%)")
            headline["konfabulationsrate"] = {"k": k, "n": n, "rate": k / n if n else 0, "ci95": [lo, hi]}
        if g == "texttreue":
            k = c["ABSTAINED"]; print(f"   => Ueberverweigerung (Text bekannt, trotzdem 'weiss nicht'): {k}/{n}")
    inco = sum(1 for d in details if "incoherent_sum" in d)
    if inco: print(f"\n[!] {inco} Fara'id-Antworten mit Summe != 1 (unplausibel)")
    print("\n" + "=" * 66)
    if a.output_json:
        json.dump({"input": a.input_jsonl, "total": len(recs), "groups": {g: dict(c) for g, c in groups.items()}, "headline": headline, "details": details},
                  open(a.output_json, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        print("[+] JSON:", a.output_json)
    if a.audit_csv:
        by_id = {r["item_id"]: r for r in recs}
        with open(a.audit_csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f); w.writerow(["item_id", "category", "verdict", "reason", "antwort_anfang"])
            for d in details:
                if d["verdict"] not in ("CORRECT", "CORRECT_VARIANT"):
                    w.writerow([d["item_id"], d["category"], d["verdict"], d["reason"], by_id[d["item_id"]].get("raw_response", "")[:240].replace("\n", " ")])
        print("[+] Audit-CSV (manuell stichprobenartig pruefen):", a.audit_csv)


if __name__ == "__main__":
    main()
