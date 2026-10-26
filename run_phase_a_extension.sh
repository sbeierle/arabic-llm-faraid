#!/usr/bin/env bash
# =============================================================================
# PHASE-A-ERWEITERUNG (nur MoE-Paar: Jais-3-MoVA-36B-A4B und Qwen3-30B-A3B), ein Modell nach dem anderen auf einer GPU.
#   1 Tokenizer-Fertilitaet (CPU)          2 Fara'id ENGLISCH (50)            3 Fara'id arabisch, 2. Seed 43 (50)
#   4 Skalierte Fallen (50) + Gegenprobe (20 echte Verse)                       5 Koranverse mit/ohne Tashkeel (2x40)
#   Basis fuer den Seed-/Sprachvergleich = arabischer Hauptlauf seed 42: wird aus $BASE_RES/<modell>/faraid.jsonl uebernommen (neu bewertet), sonst neu gelaufen.
#
#   export HF_TOKEN=hf_...                      (nur Umgebungsvariable)
#   tmux new -s ext   ->   ./run_phase_a_extension.sh
#   DRY_RUN=true ./run_phase_a_extension.sh     3 Items pro Satz (Testlauf)
#   MOCK=true ./run_phase_a_extension.sh        Attrappe ohne GPU (Pipeline-Test)
#   RESUME=true (Standard)                      fertige Saetze (score.json vorhanden) werden uebersprungen -> nach Abbruch einfach neu starten
#   MODELS_ONLY=jais3-mova ./run_phase_a_extension.sh     nur ein Modell
#   BASE_RES=results   (Standard)               Ordner des Hauptlaufs
# Ergebnis: results_ext/ERGEBNISSE_ERWEITERUNG.md  und  phase_a_extension.tar.gz
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")"
PY="${PY:-python3}"; PORT="${PORT:-8000}"; RES="${RES:-results_ext}"; LOGS="${LOGS:-logs_ext}"; BASE_RES="${BASE_RES:-results}"
DRY_RUN="${DRY_RUN:-false}"; MOCK="${MOCK:-false}"; START_TIMEOUT_MIN="${START_TIMEOUT_MIN:-60}"; SKIP_VERIFY="${SKIP_VERIFY:-false}"
GPU_UTIL="${GPU_UTIL:-0.90}"; CONC="${CONC:-8}"; RESUME="${RESUME:-true}"
JAIS3_PARSER="${JAIS3_PARSER-k2_horizon}"; JAIS3_TP="${JAIS3_TP:-1}"
[ -d /workspace ] && export HF_HOME="${BENCH_HF_HOME:-/workspace/hf_cache}"     # wie im Hauptlauf: gleicher Cache, keine zweite Modellkopie
export PYTHONUNBUFFERED=1
LIMIT=""; [ "$DRY_RUN" = "true" ] && LIMIT="--max-items 3"
# tag|HF-Repo|max-model-len|max_tokens|Sampling  (identisch zum Hauptlauf)
MODELS=("jais3-mova|inception42/Jais-3-MoVA-36B-A4B|32768|28000|T=0.7,P=0.95,K=20" "qwen3-30b-a3b|Qwen/Qwen3-30B-A3B|32768|28000|T=0.6,P=0.95,K=20")
mkdir -p "$RES" "$LOGS"
samp_args() { local s="$1" out="" p; local IFS=,; [ -z "$s" ] && { echo ""; return; }
  for p in $s; do case "${p%%=*}" in T) out="$out --temperature ${p#*=}";; P) out="$out --top-p ${p#*=}";; K) out="$out --top-k ${p#*=}";; esac; done
  echo "$out --seed ${SEED:-42}"; }
log()  { echo -e "\n\033[1;34m[$(date +%H:%M:%S)] $*\033[0m"; }
warn() { echo -e "\033[1;33m[!] $*\033[0m"; }
SERVER_PID=""
stop_server() {
  if [ -n "$SERVER_PID" ]; then kill "$SERVER_PID" 2>/dev/null; sleep 3; kill -9 "$SERVER_PID" 2>/dev/null; wait "$SERVER_PID" 2>/dev/null; fi
  pkill -9 -f "vllm.entrypoints.openai.api_server" 2>/dev/null; SERVER_PID=""
  if [ "$MOCK" != "true" ] && command -v nvidia-smi >/dev/null; then
    for _ in $(seq 1 60); do u=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1); [ "${u:-0}" -lt 2000 ] && break; sleep 2; done
  fi
}
trap stop_server EXIT

log "0/6 Umgebung"
{ echo "Zeit: $(date -Is)"; echo "Host: $(hostname)"; command -v nvidia-smi >/dev/null && nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
  echo "python: $($PY --version 2>&1)"; echo "vllm: $($PY -c 'import vllm;print(vllm.__version__)' 2>/dev/null || echo nicht-installiert)"
  echo "transformers: $($PY -c 'import transformers;print(transformers.__version__)' 2>/dev/null || echo ?)"
  echo "items:"; (cd data/items && sha256sum *.csv); echo "DRY_RUN=$DRY_RUN MOCK=$MOCK RESUME=$RESUME BASE_RES=$BASE_RES HF_HOME=${HF_HOME:-unset}"; df -h / | tail -1; } | tee "$RES/environment.log"
if [ "$MOCK" != "true" ]; then
  command -v nvidia-smi >/dev/null || { echo "[X] keine GPU (nvidia-smi fehlt). Zum Testen: MOCK=true"; exit 1; }
  $PY -c "import vllm" 2>/dev/null || { echo "[X] vLLM nicht installiert"; exit 1; }
fi
$PY -c "import scipy, numpy" 2>/dev/null || { echo "[X] scipy/numpy fehlen: pip install --break-system-packages scipy numpy"; exit 1; }
if [ "$SKIP_VERIFY" != "true" ]; then log "1/6 Daten holen und alles verifizieren"; ./verify_all.sh > "$LOGS/verify_all.log" 2>&1 || { tail -20 "$LOGS/verify_all.log"; echo "[X] verify_all fehlgeschlagen - Abbruch"; exit 1; }; tail -2 "$LOGS/verify_all.log"; fi

# ---- Fertilitaet (CPU, vor den Modellen; Fehler ist nicht fatal) ------------
log "2/6 Tokenizer-Fertilitaet"
if [ "$MOCK" = "true" ]; then FT_ARGS="--selftest"; else FT_ARGS="--models qwen3-30b-a3b=Qwen/Qwen3-30B-A3B,jais3-mova=inception42/Jais-3-MoVA-36B-A4B"; fi
if [ "$RESUME" = "true" ] && [ -f "$RES/fertility.json" ]; then echo "   schon vorhanden - uebersprungen"
else $PY scripts/fertility.py $FT_ARGS --out "$RES/fertility.json" 2>&1 | tee "$LOGS/fertility.log" | tail -25
     [ -f "$RES/fertility.json" ] || warn "Fertilitaet fehlgeschlagen (siehe $LOGS/fertility.log) - Rest laeuft trotzdem"; fi

start_server() {
  local tag=$1 id=$2 ctx=$3 extra=""
  if [[ "$tag" == jais3-* ]]; then extra="--tensor-parallel-size $JAIS3_TP"; [ -n "$JAIS3_PARSER" ] && extra="$extra --reasoning-parser $JAIS3_PARSER"; fi
  if [ "$MOCK" = "true" ]; then
    $PY scripts/mock_server.py $extra --items data/items/*.csv --port "$PORT" > "$LOGS/server_$tag.log" 2>&1 &
  else
    $PY -m vllm.entrypoints.openai.api_server --model "$id" --served-model-name "$tag" --host 127.0.0.1 --port "$PORT" \
        --dtype bfloat16 --gpu-memory-utilization "$GPU_UTIL" --max-model-len "$ctx" --trust-remote-code $extra > "$LOGS/server_$tag.log" 2>&1 &
  fi
  SERVER_PID=$!; local waited=0 max=$((START_TIMEOUT_MIN*60))
  until curl -s "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; do
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then warn "Server-Prozess ist gestorben. Letzte Logzeilen:"; tail -25 "$LOGS/server_$tag.log"; SERVER_PID=""; return 1; fi
    [ $waited -ge $max ] && { warn "Timeout ${START_TIMEOUT_MIN} min beim Serverstart"; tail -15 "$LOGS/server_$tag.log"; return 1; }
    sleep 5; waited=$((waited+5)); [ $((waited % 60)) -eq 0 ] && echo "   ... wartet auf Server ($((waited/60)) min)"
  done
  if [ "$MOCK" != "true" ]; then curl -s "http://127.0.0.1:$PORT/v1/models" | grep -q "\"$tag\"" || { warn "Servername '$tag' nicht in /v1/models"; return 1; }; fi
  return 0
}
score_set() { # tag name   (bewertet $RES/$tag/$name.jsonl)
  $PY scripts/score.py --input-jsonl "$RES/$1/$2.jsonl" --output-json "$RES/$1/$2.score.json" --audit-csv "$RES/$1/$2.audit.csv" | tee "$RES/$1/$2.report.txt" | sed -n '1,30p'
}
run_set() { # tag name csv   (Seed ueber Umgebungsvariable SEED, Standard 42)
  local tag=$1 name=$2 csv=$3
  if [ "$RESUME" = "true" ] && [ -f "$RES/$tag/$name.score.json" ] && [ "$DRY_RUN" != "true" ]; then echo "   [=] $tag/$name schon fertig - uebersprungen"; return; fi
  local mt=${MAXTOK:-1536} sa; sa=$(samp_args "${SAMP:-}")
  $PY scripts/run_eval.py --api-base "http://127.0.0.1:$PORT/v1" --model-name "$tag" --input-csv "$csv" --output-jsonl "$RES/$tag/$name.jsonl" --max-tokens "$mt" --concurrency "$CONC" $sa $LIMIT > "$LOGS/run_${tag}_$name.log" 2>&1
  local rc=$?; tail -1 "$LOGS/run_${tag}_$name.log"
  [ $rc -ne 0 ] && warn "run_eval $name: Exit $rc (einzelne Anfragen fehlgeschlagen, siehe $LOGS/run_${tag}_$name.log)"
  score_set "$tag" "$name"
}
for spec in "${MODELS[@]}"; do
  IFS='|' read -r TAG ID CTX MAXTOK SAMP <<< "$spec"; export MAXTOK SAMP
  [ -n "${MODELS_ONLY:-}" ] && [[ " ${MODELS_ONLY//,/ } " != *" $TAG "* ]] && continue
  log "3/6 Modell $TAG ($ID)"; mkdir -p "$RES/$TAG"
  # Basislauf seed 42 uebernehmen (neu bewertet mit korrigiertem Gold), falls vorhanden
  if [ -f "$BASE_RES/$TAG/faraid.jsonl" ] && [ ! -f "$RES/$TAG/faraid_s42.score.json" ]; then
    if $PY scripts/reinject.py --jsonl "$BASE_RES/$TAG/faraid.jsonl" --items data/items/faraid_eval_dataset.csv --out "$RES/$TAG/faraid_s42.jsonl"; then
      score_set "$TAG" faraid_s42; echo "BASISLAUF_UEBERNOMMEN aus $BASE_RES/$TAG/faraid.jsonl" > "$RES/$TAG/faraid_s42.herkunft"
    else warn "Basislauf-Uebernahme fehlgeschlagen -> wird neu gelaufen"; mv -f "$RES/$TAG/faraid_s42.jsonl" "$RES/$TAG/faraid_s42.fehlerhaft.jsonl" 2>/dev/null; fi
  fi
  need=0; for n in faraid_s42 faraid_en faraid_s43 traps_scaled traps_control tashkeel_on tashkeel_off; do [ -f "$RES/$TAG/$n.score.json" ] || need=1; done
  if [ "$need" = 0 ] && [ "$RESUME" = "true" ] && [ "$DRY_RUN" != "true" ]; then echo "   alle Saetze fertig - Server wird nicht gestartet"; continue; fi
  echo "gestartet" > "$RES/$TAG/STATUS"
  if ! start_server "$TAG" "$ID" "$CTX"; then
    if [[ "$TAG" == jais3-* && -n "$JAIS3_PARSER" ]]; then
      warn "Start mit --reasoning-parser $JAIS3_PARSER gescheitert, neuer Versuch ohne"; stop_server; mv "$LOGS/server_$TAG.log" "$LOGS/server_${TAG}_versuch1.log" 2>/dev/null
      P_SAVE="$JAIS3_PARSER"; JAIS3_PARSER=""; start_server "$TAG" "$ID" "$CTX"; rc_s=$?; JAIS3_PARSER="$P_SAVE"
    else rc_s=1; fi
    if [ "${rc_s:-1}" -ne 0 ]; then echo "SERVER_FEHLER" > "$RES/$TAG/STATUS"; stop_server; continue; fi
  fi
  $PY scripts/run_eval.py --api-base "http://127.0.0.1:$PORT/v1" --model-name "$TAG" --input-csv data/items/islamic_eval_dataset.csv --output-jsonl "$RES/$TAG/_smoke.jsonl" --max-items 3 --max-tokens "$MAXTOK" $(samp_args "$SAMP") > "$LOGS/smoke_$TAG.log" 2>&1
  if [ $? -ne 0 ]; then warn "Rauchtest $TAG fehlgeschlagen:"; tail -8 "$LOGS/smoke_$TAG.log"; echo "RAUCHTEST_FEHLER" > "$RES/$TAG/STATUS"; stop_server; continue; fi
  log "4/6 $TAG: Fara'id englisch";                  SEED=42 run_set "$TAG" faraid_en      data/items/faraid_en_dataset.csv
  log "4/6 $TAG: Fara'id arabisch, 2. Seed (43)";    SEED=43 run_set "$TAG" faraid_s43     data/items/faraid_eval_dataset.csv
  [ -f "$RES/$TAG/faraid_s42.score.json" ] || { log "4/6 $TAG: Fara'id arabisch seed 42 (kein Basislauf gefunden)"; SEED=42 run_set "$TAG" faraid_s42 data/items/faraid_eval_dataset.csv; }
  log "4/6 $TAG: Fallen (50)";                       SEED=42 run_set "$TAG" traps_scaled   data/items/traps_scaled.csv
  log "4/6 $TAG: Gegenprobe echte Verse (20)";       SEED=42 run_set "$TAG" traps_control  data/items/traps_control.csv
  log "4/6 $TAG: Tashkeel MIT (40)";                 SEED=42 run_set "$TAG" tashkeel_on    data/items/quran_tashkeel_on.csv
  log "4/6 $TAG: Tashkeel OHNE (40)";                SEED=42 run_set "$TAG" tashkeel_off   data/items/quran_tashkeel_off.csv
  echo "OK" > "$RES/$TAG/STATUS"; stop_server
done

log "5/6 Bericht"
$PY scripts/ext_report.py --res "$RES" && sed -n '1,60p' "$RES/ERGEBNISSE_ERWEITERUNG.md"
log "6/6 Paket"
mkdir -p "$RES/items_ext" && cp data/items/faraid_en_dataset.csv data/items/traps_scaled.csv data/items/traps_control.csv data/items/quran_tashkeel_on.csv data/items/quran_tashkeel_off.csv data/items/SHA256SUMS "$RES/items_ext/"
tar czf phase_a_extension.tar.gz "$RES" "$LOGS" && echo -e "\n[+] Alles zum Herunterladen: $(pwd)/phase_a_extension.tar.gz"
