# Extension 5 (v1.2): disagreement between schools and a context test

Part of the package for the preprint *Arabic LLMs in Practice: Jais-3 vs. Qwen on Islamic Inheritance Law (Fara'id), Scriptural Traps and Tokenizer Economics* (v1.2). Extensions 1 to 4 and everything in the repository root are unchanged from v1.0.

**Status.** Sample evaluation, not a benchmark. Ten disputed fiqh questions, two models (Jais-3-MoVA-36B-A4B and Qwen3-30B-A3B), three runs each at temperature 0.7. The answer key was built by the author with Claude's help and scored without blinding. **Neither Islamic legal scholars nor native speakers of Arabic reviewed the questions, the answer key or the Arabic texts.** This is not a fatwā.

## What is in here

| Path | Content |
| --- | --- |
| `prompts/fiqh_questions_v2.jsonl` | the 10 disputed questions plus 4 consensus controls of the 14-question run |
| `prompts/fiqh_pilot_gold_v3.jsonl` | answer key per question and voice (German notes, source references, status `belegt` / `indirekt` / `nicht gefunden`) |
| `prompts/fiqh_v12_prompts_no_ctx.jsonl` | context-test prompts of the condition *no context* (10) |
| `prompts/fiqh_v12_usul_closed_book.jsonl`, `prompts/usul_spec.json` | 7 Usul cases: closed-book prompts, criteria checklists, text anchors |
| `corpus_manifest.json` | the 190 retrieval passages of the context test: question, source family, URL, length, SHA-256. **No passage text.** |
| `results/*.json` | answers of both models, one file per run set, **without the raw output and thinking text** (`raw`, `reasoning`) |
| `results/FULL_FILES.sha256` | SHA-256 of the full originals, which are available from the author on request |
| `scoring/fiqh_v12_gold_scoring.csv` | 1,296 scored cells (model, condition, question, voice, run, verdict) |
| `scoring/fiqh_v2_scoring.csv` | scored cells of the 14-question run |
| `scripts/` | runner, corpus builder, rule-based classifier, scorers, scrapers, vLLM start script |
| `reproduce_scoring.sh` | recomputes all tables from `results/` and checks the CSV files byte for byte |

## Recompute the scoring (2 minutes, no GPU)

```bash
bash fiqh_v12/reproduce_scoring.sh
```

It prints the tables of the report (right / partly / wrong / null per condition, Usul keyword hits, the 14-question comparison, identical-wording runs) and ends with `... identical` for both CSV files.

## Rebuild the retrieval corpus

The passages are text of third-party websites and books and are not redistributed.

1. Scrape the pages listed in `corpus_manifest.json` (`scripts/fiqh_cdp_scrape.py`, `scripts/fiqh_cdp_scrape_gaps.py`; they drive a local Chrome over CDP).
2. `python scripts/build_v12.py` builds the prompts with context (`fiqh_v12_rag_prompts.jsonl`, `fiqh_v12_usul_prompts.jsonl`).
3. Compare the SHA-256 of each rebuilt passage with `corpus_manifest.json`. Sites change, so a mismatch means the page changed, not necessarily that something went wrong.

## Re-run the models

The scripts assume the pod layout `/workspace/fiqh_eval` of the original run. Serve one model with vLLM (context 16,384; `scripts/start_vllm.sh`; on the original pod the equivalent `python3 -m vllm.entrypoints.openai.api_server ... --dtype bfloat16` was used and the vLLM version was not recorded again), then:

```bash
python run_fiqh_v12.py 3 0.7 4 all jais      # or: ... all qwen
python run_fiqh_v2_model.py ...              # 14-question run, see the header of the script
```

Only temperature (0.7) and the token limit (7,000 for the context test) are set; all other sampling values are the server defaults. Sampling is not repeatable bit for bit.

## Data policy

As in v1.0: no raw hadith text, no unmodified Quran text, no third-party passages. The gold file contains short German notes and source references written by the author. Model outputs are published without raw text and thinking text because they can quote scripture and source passages.

## Add your own questions

If you are a scholar or a native speaker and want to check or extend the questions, send me questions with answer keys you have checked, in the format of `prompts/fiqh_questions_v2.jsonl` (`id`, `thema`, `frage_ar`) and `prompts/fiqh_pilot_gold_v3.jsonl` (per voice: position, source reference, status). I will re-run the test with them and publish the result next to the existing one. Contact: stefan.beierle@pm.me or open an issue in this repository.

## Known limits

Ten questions, two models, one hardware setup. The retrieval corpus contains the pages the answer key comes from, so *oracle* and *retrieved* results are an upper bound and no evidence that retrieval closes the gap. The rule-based classifier agrees with hand verdicts in 98% (Jais) and 99% (Qwen) of the classified cells; about 16% of the cells are unclassifiable and left out. Full list in the report, Extension 5 and Corrections 11 to 14.

## License

As in the repository root: code MIT; task files and results created by the author CC BY 4.0; third-party text is not covered and not included.
