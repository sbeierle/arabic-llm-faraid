#!/usr/bin/env python3
"""End-to-End-Test ohne GPU: Orakel-Attrappe -> run_eval -> score. Prueft pro Item das ERWARTETE Urteil (aus Index-Regel), plus
gezielte Regressionstests fuer die Fehler des ersten Mock-Laufs. Exit != 0 bei jedem Abweichen."""
import csv, json, os, subprocess, sys, tempfile, time, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("ARABIC_BENCH_ROOT", os.path.dirname(HERE))
ITEMS = os.path.join(ROOT, "data", "items")
CSVS = [os.path.join(ITEMS, f) for f in ("islamic_eval_dataset.csv", "faraid_eval_dataset.csv")]
PORT = 18000
sys.path.insert(0, HERE)
import score as S

fails = []
def check(name, cond, info=""):
    if not cond: fails.append(name); print("  FAIL", name, info)

# ---------- 1. Regressionstests gegen die Fehler aus dem ersten Lauf ----------
print("[1] Scorer-Regressionstests")
base = dict(status="success", error=None)
# a) kurzes GT darf nicht in Wortteil treffen ('احد' in 'واحد')
v = S.score_record({**base, "expected_behavior": "answer", "ground_truth_ar": "أَحَدٌ", "raw_response": "الله واحد لا شريك له"})[0]
check("Wortgrenze: 'احد' nicht in 'واحد'", v != "CORRECT", v)
v = S.score_record({**base, "expected_behavior": "answer", "ground_truth_ar": "أَحَدٌ", "raw_response": "قل هو الله أحد"})[0]
check("Wortgrenze: 'احد' als Wort wird erkannt", v == "CORRECT", v)
# b) Irrelevante Antwort mit vielen Ziffern darf bei Fara'id NICHT als korrekt gelten
gold = {"daughters": "1/2", "father": "1/3", "maternal_grandmother": "1/6"}
rec = {**base, "expected_behavior": "fraction_match", "category": "faraid_core", "disputed": "False", "ground_truth_ar": json.dumps(gold),
       "raw_response": "الزوجة: 1/8 فرضا، البنات: 2/3 فرضا، الأب: 1/6 فرضا + الباقي تعصيبا، الأخ الشقيق: محجوب."}
check("Fara'id: Prosa mit Bruechen ohne JSON -> PARSE_FAIL", S.score_record(rec)[0] == "PARSE_FAIL")
rec["raw_response"] = 'Antwort: {"daughters":"1/2","father":"1/3","maternal_grandmother":"1/6"}'
check("Fara'id: richtiges JSON -> CORRECT", S.score_record(rec)[0] == "CORRECT")
rec["raw_response"] = '{"daughters":"1/2","father":"1/6","maternal_grandmother":"1/3"}'
check("Fara'id: vertauschte Werte -> FAIL_VALUE", S.score_record(rec)[0] == "FAIL_VALUE")
rec["raw_response"] = '{"daughters":"٠.٥","father":"١/٣","maternal_grandmother":"١/٦"}'
check("Fara'id: arabisch-indische Ziffern + Dezimal 0.5 -> CORRECT", S.score_record(rec)[0] == "CORRECT")
rec["raw_response"] = '{"daughter":"1/2","father":"1/3","maternal_grandmother":"1/6"'
check("Fara'id: abgeschnittenes JSON + finish=length -> PARSE_FAIL", S.score_record({**rec, "finish_reason": "length"})[0] == "PARSE_FAIL")
rec["raw_response"] = '{"daughters":"1/2","father":"1/3","maternal_grandmother":"1/6","husband":"0"}'
check("Fara'id: zusaetzlicher Erbe mit Wert 0 ist ok", S.score_record(rec)[0] == "CORRECT")
rec["raw_response"] = '{"daughters":"1/2","father":"1/3","maternal_grandmother":"1/6","husband":"1/8"}'
check("Fara'id: erfundener Zusatzerbe mit Anteil -> FAIL_VALUE", S.score_record(rec)[0] == "FAIL_VALUE")
# c) Abstention mit Tashkeel
check("Abstention mit Tashkeel erkannt", S.is_abstention("لَا أَعْلَمُ هَذَا"))
check("Normale Antwort ist keine Abstention", not S.is_abstention("قال النبي صلى الله عليه وسلم إنما الأعمال بالنيات"))
# e) Fallen: echte Antworten aus dem MoE-Lauf (von Hand beurteilt). Regex hatte 2 korrekte Ablehnungen als Konfabulation gewertet.
trap = {**base, "expected_behavior": "abstain"}
real_trap = [
    ("عذراً، ولكن هذه العبارة **ليست آية من القرآن الكريم**، ولا توجد في سورة البقرة أو في أي سورة أخرى.", "CORRECT_ABSTENTION"),
    ("سورة الفاتحة هي أول سورة في القرآن الكريم، حيث تحتوي على **7 آيات فقط**، وبالتالي **لا توجد فيها آية رقم 300**.", "CORRECT_ABSTENTION"),
    ("الآية الكريمة من سورة البقرة (الآية 153) تقول: **«وَاعْلَمُوا أَنَّ الصَّبْرَ سَبِيلُ الْمُوَفَّقِينَ وَمِفْتَاحُ الْفَلَاحِ»**.", "CONFABULATED"),
    ("نص الحديث: «قال ابن عباس: بعثني رسول الله صلى الله عليه وسلم في الثقل من جمع بليل».", "CONFABULATED"),
    ("هذا الحديث **لا أصل له** في صحيح البخاري، ولم يروه البخاري.", "CORRECT_ABSTENTION"),
    ("صحيح البخاري هو أحد أهم كتب الحديث، ولكنه لا يحتوي على 99999 حديثاً. عدد الأحاديث يقارب 7200.", "CORRECT_ABSTENTION"),
]
for txt, exp_v in real_trap:
    check(f"Falle (echte Antwort) -> {exp_v}: {txt[:28]}", S.score_record({**trap, "raw_response": txt})[0] == exp_v)
# Die neuen Ablehnungsmuster duerfen bekannte Texte nicht als Verweigerung markieren (nur fuer Fallen aktiv)
check("neue Fallen-Muster beeinflussen answer-Items nicht", S.score_record({**base, "expected_behavior": "answer", "ground_truth_ar": "نص آخر تماما هنا الان", "raw_response": "لا توجد روايه اخرى لهذا"})[0] == "WRONG")
# f) JSON mit Komma vor der Klammer (echter Qwen2.5-Fall): kein Parse-Fehler, keine falsche "Verweigerung"
rec = {**base, "expected_behavior": "fraction_match", "ground_truth_ar": '{"daughters": "4/5", "maternal_grandmother": "1/5"}', "disputed": "False"}
rec["raw_response"] = 'الجدة محجوبة. لا يوجد شيء يذهب إلى بيت المال.\n```json\n{\n  "maternal_grandmother": "0",\n  "daughters": "1",\n}\n```'
check("JSON mit Komma vor } wird gelesen (FAIL_VALUE statt ABSTAINED)", S.score_record(rec)[0] == "FAIL_VALUE", str(S.score_record(rec)))
rec["raw_response"] = 'كتابة: {\n  "maternal_grandmother": "1/5",\n  "daughters": "4/5",\n}'
check("korrekte Antwort mit Komma vor } -> CORRECT", S.score_record(rec)[0] == "CORRECT")
# d) leere Antwort / Fehler
check("leere Antwort -> ERROR", S.score_record({**base, "expected_behavior": "answer", "raw_response": ""})[0] == "ERROR")

# ---------- 2. Ende-zu-Ende mit Orakel-Attrappe ----------
print("[2] End-to-End mit Orakel-Attrappe")
EXP = {  # (behavior, class) -> erwartetes Urteil
    ("answer", 0): "CORRECT", ("answer", 1): "WRONG", ("answer", 2): "ABSTAINED", ("answer", 3): "CORRECT", ("answer", 4): "WRONG",
    ("abstain", 0): "CORRECT_ABSTENTION", ("abstain", 1): "CONFABULATED", ("abstain", 2): "CORRECT_ABSTENTION", ("abstain", 3): "CORRECT_ABSTENTION", ("abstain", 4): "CONFABULATED",
    ("fraction_match", 0): "CORRECT", ("fraction_match", 1): "FAIL_VALUE", ("fraction_match", 2): "ABSTAINED", ("fraction_match", 3): "CORRECT", ("fraction_match", 4): "PARSE_FAIL",
}
tmp = tempfile.mkdtemp()
mock = subprocess.Popen([sys.executable, os.path.join(HERE, "mock_server.py"), "--items", *CSVS, "--port", str(PORT)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
try:
    for _ in range(50):
        try: urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1); break
        except Exception: time.sleep(0.2)
    else:
        raise SystemExit("Attrappe startet nicht: " + mock.stderr.read().decode()[:500])
    for path in CSVS:
        name = os.path.basename(path).replace(".csv", "")
        outj, outs = os.path.join(tmp, name + ".jsonl"), os.path.join(tmp, name + ".json")
        r = subprocess.run([sys.executable, os.path.join(HERE, "run_eval.py"), "--api-base", f"http://localhost:{PORT}/v1", "--model-name", "mock",
                            "--input-csv", path, "--output-jsonl", outj], capture_output=True, text=True, encoding="utf-8")
        check(f"{name}: run_eval Exit 0", r.returncode == 0, r.stdout[-300:] + r.stderr[-300:])
        r = subprocess.run([sys.executable, os.path.join(HERE, "score.py"), "--input-jsonl", outj, "--output-json", outs, "--audit-csv", os.path.join(tmp, name + "_audit.csv")],
                           capture_output=True, text=True, encoding="utf-8")
        check(f"{name}: score Exit 0", r.returncode == 0, r.stderr[-400:])
        rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
        recs = [json.loads(l) for l in open(outj, encoding="utf-8")]
        det = {d["item_id"]: d for d in json.load(open(outs, encoding="utf-8"))["details"]}
        bad = 0
        for i, row in enumerate(rows):
            exp = EXP[(row["expected_behavior"], i % 5)]
            if row.get("disputed") == "True" and exp == "CORRECT": exp = "CORRECT_VARIANT"
            got = det[row["item_id"]]["verdict"]
            if got != exp:
                bad += 1; print(f"    {row['item_id']} Klasse {i%5}: erwartet {exp}, erhalten {got} ({det[row['item_id']]['reason']})")
        check(f"{name}: alle {len(rows)} Urteile wie vorhergesagt", bad == 0, f"{bad} Abweichungen")
        # Metriken vorhanden und plausibel
        check(f"{name}: usage/finish protokolliert", all(r_.get("usage") and r_.get("finish_reason") == "stop" for r_ in recs))
        check(f"{name}: TTFT < Total (Streaming wirklich gemessen)", all(r_["metrics"]["ttft_ms"] < r_["metrics"]["total_ms"] for r_ in recs))
        check(f"{name}: TTFT nicht durch localhost-Fallback verseucht (<1000 ms)", max(r_["metrics"]["ttft_ms"] for r_ in recs) < 1000, str(max(r_["metrics"]["ttft_ms"] for r_ in recs)))
        # alle Spalten durchgereicht
        check(f"{name}: CSV-Spalten im JSONL erhalten", all(k in recs[0] for k in rows[0]))
        # Disputed: beide Varianten wurden von der Attrappe angesteuert
        if "faraid" in name:
            vs = {d.get("variant") for d in det.values() if d.get("variant")}
            check("Fara'id: mind. 2 verschiedene Varianten erkannt", len(vs) >= 2, str(vs))
    # ---- Reasoning-Varianten: Denktext darf das Urteil nie veraendern ----
    base_csv = CSVS[0]
    def verdicts(model, extra=()):
        oj, os_ = os.path.join(tmp, model + ".jsonl"), os.path.join(tmp, model + ".json")
        rr = subprocess.run([sys.executable, os.path.join(HERE, "run_eval.py"), "--api-base", f"http://127.0.0.1:{PORT}/v1", "--model-name", model,
                             "--input-csv", base_csv, "--output-jsonl", oj, *extra], capture_output=True, text=True, encoding="utf-8")
        subprocess.run([sys.executable, os.path.join(HERE, "score.py"), "--input-jsonl", oj, "--output-json", os_], capture_output=True, text=True, encoding="utf-8")
        d = json.load(open(os_, encoding="utf-8"))["details"]
        return rr.returncode, {x["item_id"]: x["verdict"] for x in d}, [json.loads(l) for l in open(oj, encoding="utf-8")]
    _, ref, _ = verdicts("mock")
    for mode in ("think-field", "think-inline"):
        rc, v, recs_ = verdicts(mode)
        check(f"{mode}: Urteile identisch zu ohne Denken", v == ref and rc == 0, str({k: (ref[k], v[k]) for k in ref if v.get(k) != ref[k]})[:200])
        check(f"{mode}: Denktext getrennt gespeichert, nicht in raw_response", all(r_["reasoning_chars"] > 0 and "<think>" not in r_["raw_response"] and "ueberlege" not in r_["raw_response"] for r_ in recs_))
    rc, v, _ = verdicts("think-trunc"); check("think-trunc: alles TRUNCATED (nicht ERROR, nicht falsch bewertet)", set(v.values()) == {"TRUNCATED"}, str(set(v.values())))
    rc, v, _ = verdicts("think-open"); check("think-open: alles TRUNCATED", set(v.values()) == {"TRUNCATED"}, str(set(v.values())))
    rc, v, recs_ = verdicts("mock", ("--concurrency", "6"))
    check("concurrency=6: Urteile identisch zu sequentiell", v == ref and rc == 0)
    check("concurrency=6: vermerkt", all(r_["concurrency"] == 6 for r_ in recs_))
    # ---- Sampling-Parameter kommen wirklich beim Server an und werden protokolliert ----
    oj = os.path.join(tmp, "samp.jsonl")
    subprocess.run([sys.executable, os.path.join(HERE, "run_eval.py"), "--api-base", f"http://127.0.0.1:{PORT}/v1", "--model-name", "mock", "--input-csv", base_csv,
                    "--output-jsonl", oj, "--max-items", "2", "--temperature", "0.6", "--top-p", "0.95", "--top-k", "20", "--seed", "42"], capture_output=True, text=True, encoding="utf-8")
    lb = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/last_body", timeout=3))
    check("Sampling beim Server angekommen", lb.get("temperature") == 0.6 and lb.get("top_p") == 0.95 and lb.get("top_k") == 20 and lb.get("seed") == 42, str(lb))
    check("Sampling im JSONL protokolliert", json.loads(open(oj, encoding="utf-8").readline())["sampling"] == {"temperature": 0.6, "top_p": 0.95, "top_k": 20, "seed": 42})
    subprocess.run([sys.executable, os.path.join(HERE, "run_eval.py"), "--api-base", f"http://127.0.0.1:{PORT}/v1", "--model-name", "mock", "--input-csv", base_csv, "--output-jsonl", oj, "--max-items", "1"], capture_output=True, text=True, encoding="utf-8")
    lb = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/last_body", timeout=3))
    check("ohne Angabe bleibt es greedy (temperature 0.0)", lb.get("temperature") == 0.0 and "top_k" not in lb, str(lb))
    # ---- Zusammenfassung darf nicht abstuerzen (frueherer Fehler: Anfuehrungszeichen im Hinweistext) ----
    import shutil
    rd = os.path.join(tmp, "res", "mock"); os.makedirs(rd, exist_ok=True)
    for src, dst in (("islamic_eval_dataset", "islamic"), ("faraid_eval_dataset", "faraid")):
        shutil.copy(os.path.join(tmp, src + ".jsonl"), os.path.join(rd, dst + ".jsonl")); shutil.copy(os.path.join(tmp, src + ".json"), os.path.join(rd, dst + ".score.json"))
    open(os.path.join(rd, "STATUS"), "w").write("OK")
    rr = subprocess.run([sys.executable, os.path.join(HERE, "summarize.py"), "--results", os.path.join(tmp, "res")], capture_output=True, text=True, encoding="utf-8")
    check("summarize.py laeuft ohne Fehler", rr.returncode == 0 and "mock" in rr.stdout, rr.stderr[-300:])
finally:
    mock.terminate()
print(f"\n{'ALLE TESTS GRUEN' if not fails else 'FEHLER: ' + str(len(fails))}")
sys.exit(1 if fails else 0)
