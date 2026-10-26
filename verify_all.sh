#!/usr/bin/env bash
# Ein Befehl: Daten holen, Items neu bauen, alles verifizieren. Exit != 0 bei jedem Fehler.
set -euo pipefail
cd "$(dirname "$0")"
./bootstrap_data.sh
# 0) Integritaet der AUSGELIEFERTEN Items (vor dem Neubau!)
if [ -f data/items/SHA256SUMS ]; then (cd data/items && sha256sum -c SHA256SUMS) || { echo "[X] ausgelieferte Items veraendert"; exit 1; }; fi
cd scripts
python3 -m py_compile *.py && echo "[+] alle Skripte syntaktisch ok"
bash -n ../run_phase_a.sh ../run_phase_a_extension.sh ../verify_all.sh ../bootstrap_data.sh ../preflight_check.sh && echo "[+] Shell-Skripte syntaktisch ok"
python3 test_faraid_core.py
python3 build_hadith_items.py
python3 verify_items.py
python3 build_faraid_items.py
python3 verify_faraid.py
python3 build_extension_items.py
python3 verify_extension.py
python3 test_pipeline.py
# Reproduzierbarkeit: neu gebaute Dateien muessen mit den ausgelieferten identisch sein
cd ../data/items
sha256sum *.csv > SHA256SUMS.new
if [ -f SHA256SUMS ]; then diff SHA256SUMS SHA256SUMS.new && echo "[+] Items byte-identisch mit den ausgelieferten (SHA256SUMS)"; else mv SHA256SUMS.new SHA256SUMS; fi
rm -f SHA256SUMS.new
echo "ALLES GRUEN"
