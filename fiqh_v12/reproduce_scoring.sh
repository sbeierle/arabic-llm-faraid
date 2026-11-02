#!/usr/bin/env bash
# Recomputes the scoring tables of Extension 5 from the published (slim) results files.
# Needs only Python 3. Run from anywhere:  bash fiqh_v12/reproduce_scoring.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT
mkdir -p "$W/v12"
cp "$HERE"/scripts/*.py "$W"/
cp "$HERE"/results/fiqh_v12_results_*.json "$W"/
cp "$HERE"/results/fiqh_runs_v2_qwen.json "$W/v12/"
cp "$HERE"/results/fiqh_runs_v2_jais.json "$W/runs_reparsed.json"
cd "$W"
echo "== v1.2 context test: right/partly/wrong/null per condition and model"; python3 -I score_v12_gold.py
echo; echo "== Usul keyword hits"; python3 -I score_usul.py
echo; echo "== 14-question run (v2): Jais vs Qwen"; python3 -I score_v2.py >/dev/null; python3 -I score_qwen_v2.py
echo; echo "== diff against the published CSV (no output below = identical)"
diff <(tr -d '\r' < fiqh_v12_gold_scoring.csv) <(tr -d '\r' < "$HERE"/scoring/fiqh_v12_gold_scoring.csv) && echo "fiqh_v12_gold_scoring.csv identical"
diff <(tr -d '\r' < fiqh_v2_scoring.csv) <(tr -d '\r' < "$HERE"/scoring/fiqh_v2_scoring.csv) && echo "fiqh_v2_scoring.csv identical"
