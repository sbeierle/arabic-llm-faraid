#!/usr/bin/env bash
# =============================================================================
# PHASE A: Genauigkeit Qwen2.5-32B vs Jais-3-32B (Hadith/Koran/Fallen/Fara'id). Ein Modell nach dem anderen auf einer GPU.
#   export HF_TOKEN=hf_...           (nur Umgebungsvariable; wird nie geloggt/gespeichert)
#   ./run_phase_a.sh                 voller Lauf
#   DRY_RUN=true ./run_phase_a.sh    nur 3 Items pro Datei (Testlauf, ~Minuten + Modell-Download)
#   MODELS_ONLY=jais3-32b ./run_phase_a.sh    nur ein Modell (Tags: qwen25-32b, jais3-32b, optional jais30b-legacy)
#   WITH_LEGACY=true ./run_phase_a.sh         zusaetzlich altes Jais-30B-chat-v3 (Vergleich alt/neu)
#   WITH_MOE=true ./run_phase_a.sh            zusaetzlich MoE-Paar: Jais-3-MoVA-36B-A4B und Qwen3-30B-A3B (+ ca. 130 GB Platte)
#   CONC=8 (Standard)                         parallele Anfragen -> schnell, aber TTFT/Tok/s dann KEINE Latenzmessung
#   JAIS3_PARSER=<name>                       optional vLLM --reasoning-parser fuer Jais-3 (Name laut Modellkarte/vLLM-Version)
#   JAIS3_TP=1 (Standard)                     Tensor-Parallel; Modellkarte nennt TP=2 im Beispiel
#   MOCK=true ./run_phase_a.sh       KEIN vLLM, Attrappe (nur zum Testen der Pipeline)
# Ein fehlgeschlagenes Modell bricht NICHT alles ab (teure GPU-Zeit): Status steht in results/<modell>/STATUS.
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")"
PY="${PY:-python3}"; PORT="${PORT:-8000}"; RES="${RES:-results}"; LOGS="${LOGS:-logs}"
DRY_RUN="${DRY_RUN:-false}"; MOCK="${MOCK:-false}"; START_TIMEOUT_MIN="${START_TIMEOUT_MIN:-60}"; SKIP_VERIFY="${SKIP_VERIFY:-false}"
GPU_UTIL="${GPU_UTIL:-0.90}"; CONC="${CONC:-8}"; WITH_LEGACY="${WITH_LEGACY:-false}"; WITH_MOE="${WITH_MOE:-false}"
JAIS3_PARSER="${JAIS3_PARSER-k2_horizon}"; JAIS3_TP="${JAIS3_TP:-1}"   # Parser-Standard laut Modellkarte; JAIS3_PARSER= (leer) schaltet ihn ab
# HF_HOME wird bewusst NICHT aus der Umgebung uebernommen (RunPod setzt z. B. /workspace/.cache/huggingface -> Doppelkopien, Platte voll). Ueberschreiben nur mit BENCH_HF_HOME.
[ -d /workspace ] && export HF_HOME="${BENCH_HF_HOME:-/workspace/hf_cache}"
export PYTHONUNBUFFERED=1
LIMIT=""; [ "$DRY_RUN" = "true" ] && LIMIT="--max-items 3"
# Format: tag|HF-Repo|max-model-len|max_tokens|Sampling   (leer = greedy; T=Temperatur, P=top_p, K=top_k)
# Sampling der Reasoning-Modelle = Herstellerempfehlung (Qwen3: Greedy ist im Denkmodus ausdruecklich NICHT empfohlen, fuehrt zu Endlosschleifen;
# Jais-3-MoVA-Karte: Arabisch/Denken T=0.7, P=0.95, K=20; fuer Jais-3-32B dieselben Werte uebernommen = NICHT geprueft). GREEDY=true erzwingt Greedy fuer alle.
MODELS=("qwen25-32b|Qwen/Qwen2.5-32B-Instruct|8192|1536|" "jais3-32b|inception42/Jais-3-32B|32768|28000|T=0.7,P=0.95,K=20")
[ "$WITH_MOE" = "true" ] && MODELS+=("jais3-mova|inception42/Jais-3-MoVA-36B-A4B|32768|28000|T=0.7,P=0.95,K=20" "qwen3-30b-a3b|Qwen/Qwen3-30B-A3B|32768|28000|T=0.6,P=0.95,K=20")
[ "$WITH_LEGACY" = "true" ] && MODELS+=("jais30b-legacy|inceptionai/jais-30b-chat-v3|8192|1536|")
# HINWEIS: inception42/Jais-3-32B-Uno ist KEIN Chat-Modell, sondern ein Speculative-Decoding-Adapter und mit normalem vLLM nicht ladbar.
mkdir -p "$RES" "$LOGS"
samp_args() { # "T=0.7,P=0.95,K=20" -> CLI-Argumente; leer oder GREEDY=true -> nichts (greedy)
  local s="$1" out="" p; local IFS=,
  if [ "${GREEDY:-false}" = "true" ] || [ -z "$s" ]; then echo ""; return; fi
  for p in $s; do case "${p%%=*}" in T) out="$out --temperature ${p#*=}";; P) out="$out --top-p ${p#*=}";; K) out="$out --top-k ${p#*=}";; esac; done
  echo "$out --seed ${SEED:-42}"
}
log()  { echo -e "\n\033[1;34m[$(date +%H:%M:%S)] $*\033[0m"; }
warn() { echo -e "\033[1;33m[!] $*\033[0m"; }
SERVER_PID=""
stop_server() {
  if [ -n "$SERVER_PID" ]; then kill "$SERVER_PID" 2>/dev/null; sleep 3; kill -9 "$SERVER_PID" 2>/dev/null; wait "$SERVER_PID" 2>/dev/null; fi
  pkill -9 -f "vllm.entrypoints.openai.api_server" 2>/dev/null; SERVER_PID=""
  if [ "$MOCK" != "true" ] && command -v nvidia-smi >/dev/null; then   # GPU-Speicher muss frei sein, sonst scheitert das naechste Modell
    for _ in $(seq 1 60); do u=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1); [ "${u:-0}" -lt 2000 ] && break; sleep 2; done
  fi
}
trap stop_server EXIT

# ---- 0. Umgebung festhalten ------------------------------------------------
log "0/5 Umgebung"
{ echo "Zeit: $(date -Is)"; echo "Host: $(hostname)"; command -v nvidia-smi >/dev/null && nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
  echo "python: $($PY --version 2>&1)"; echo "vllm: $($PY -c 'import vllm;print(vllm.__version__)' 2>/dev/null || echo nicht-installiert)"
  echo "transformers: $($PY -c 'import transformers;print(transformers.__version__)' 2>/dev/null || echo ?)"
  echo "items:"; (cd data/items && sha256sum *.csv); echo "DRY_RUN=$DRY_RUN MOCK=$MOCK"; echo "HF_HOME=${HF_HOME:-unset}"; df -h / | tail -1; } | tee "$RES/environment.log"
if [ "$MOCK" != "true" ]; then
  [ -z "${HF_TOKEN:-}" ] && warn "HF_TOKEN nicht gesetzt (ok fuer oeffentliche Modelle; bei 401/403 beim Download: export HF_TOKEN=hf_...)"
  command -v nvidia-smi >/dev/null || { echo "[X] keine GPU (nvidia-smi fehlt). Zum Testen: MOCK=true"; exit 1; }
  VLLM_V=$($PY -c 'import vllm;print(vllm.__version__)' 2>/dev/null || echo "")
  if [ -n "$VLLM_V" ] && ! $PY -c "import sys;from packaging.version import Version as V;sys.exit(0 if V('$VLLM_V')>=V('0.30.0') else 1)" 2>/dev/null; then warn "vLLM $VLLM_V < 0.30.0: Jais-3-32B laut Modellkarte evtl. nicht ladbar (Qwen laeuft). Ggf. pip install -U vllm in frischer venv."; fi
  $PY -c "import vllm" 2>/dev/null || { echo "[X] vLLM nicht installiert: pip install vllm  (oder RunPod-vLLM-Template nutzen)"; exit 1; }
fi

# ---- 1. Daten + Tests ------------------------------------------------------
if [ "$SKIP_VERIFY" != "true" ]; then log "1/5 Daten holen und alles verifizieren"; ./verify_all.sh > "$LOGS/verify_all.log" 2>&1 || { tail -20 "$LOGS/verify_all.log"; echo "[X] verify_all fehlgeschlagen - Abbruch (Items/Skripte nicht vertrauenswuerdig)"; exit 1; }; tail -2 "$LOGS/verify_all.log"; fi

# ---- Hilfsfunktionen -------------------------------------------------------
start_server() { # tag id ctx
  local tag=$1 id=$2 ctx=$3 extra=""
  if [[ "$tag" == jais3-* ]]; then extra="--tensor-parallel-size $JAIS3_TP"; [ -n "$JAIS3_PARSER" ] && extra="$extra --reasoning-parser $JAIS3_PARSER"; fi
  if [ "$MOCK" = "true" ]; then
    $PY scripts/mock_server.py $extra --items data/items/islamic_eval_dataset.csv data/items/faraid_eval_dataset.csv data/items/calibration_set.csv --port "$PORT" > "$LOGS/server_$tag.log" 2>&1 &
  else
    $PY -m vllm.entrypoints.openai.api_server --model "$id" --served-model-name "$tag" --host 127.0.0.1 --port "$PORT" \
        --dtype bfloat16 --gpu-memory-utilization "$GPU_UTIL" --max-model-len "$ctx" --trust-remote-code $extra > "$LOGS/server_$tag.log" 2>&1 &
  fi
  SERVER_PID=$!
  local waited=0 max=$((START_TIMEOUT_MIN*60))
  until curl -s "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; do
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then warn "Server-Prozess ist gestorben. Letzte Logzeilen:"; tail -25 "$LOGS/server_$tag.log"; SERVER_PID=""; return 1; fi
    [ $waited -ge $max ] && { warn "Timeout ${START_TIMEOUT_MIN} min beim Serverstart"; tail -15 "$LOGS/server_$tag.log"; return 1; }
    sleep 5; waited=$((waited+5)); [ $((waited % 60)) -eq 0 ] && echo "   ... wartet auf Server ($((waited/60)) min; erster Start laedt das Modell herunter)"
  done
  if [ "$MOCK" != "true" ]; then curl -s "http://127.0.0.1:$PORT/v1/models" | grep -q "\"$tag\"" || { warn "Servername '$tag' nicht in /v1/models"; return 1; }; fi
  return 0
}
run_set() { # tag name csv
  local tag=$1 name=$2 csv=$3
  local mt=${MAXTOK:-1536} sa; sa=$(samp_args "${SAMP:-}")
  $PY scripts/run_eval.py --api-base "http://127.0.0.1:$PORT/v1" --model-name "$tag" --input-csv "$csv" --output-jsonl "$RES/$tag/$name.jsonl" --max-tokens "$mt" --concurrency "$CONC" $sa $LIMIT > "$LOGS/run_${tag}_$name.log" 2>&1
  local rc=$?; tail -1 "$LOGS/run_${tag}_$name.log"
  [ $rc -ne 0 ] && warn "run_eval $name: Exit $rc (einzelne Anfragen fehlgeschlagen, siehe $LOGS/run_${tag}_$name.log)"
  $PY scripts/score.py --input-jsonl "$RES/$tag/$name.jsonl" --output-json "$RES/$tag/$name.score.json" --audit-csv "$RES/$tag/$name.audit.csv" | tee "$RES/$tag/$name.report.txt" | sed -n '1,40p'
}
FIRST=1
for spec in "${MODELS[@]}"; do
  IFS='|' read -r TAG ID CTX MAXTOK SAMP <<< "$spec"; export MAXTOK SAMP
  [ -n "${MODELS_ONLY:-}" ] && [[ " ${MODELS_ONLY//,/ } " != *" $TAG "* ]] && continue   # MODELS_ONLY="a,b" moeglich
  log "2/5 Modell $TAG ($ID)"; mkdir -p "$RES/$TAG"; echo "gestartet" > "$RES/$TAG/STATUS"
  if ! start_server "$TAG" "$ID" "$CTX"; then
    if [[ "$TAG" == jais3-* && -n "$JAIS3_PARSER" ]]; then   # evtl. kennt diese vLLM-Version den Parser nicht -> einmal ohne versuchen
      warn "Start mit --reasoning-parser $JAIS3_PARSER gescheitert, neuer Versuch ohne (Denktext landet dann im Antworttext)"; stop_server; mv "$LOGS/server_$TAG.log" "$LOGS/server_${TAG}_versuch1.log" 2>/dev/null
      P_SAVE="$JAIS3_PARSER"; JAIS3_PARSER=""; start_server "$TAG" "$ID" "$CTX"; rc_s=$?; JAIS3_PARSER="$P_SAVE"
    else rc_s=1; fi
    if [ "${rc_s:-1}" -ne 0 ]; then echo "SERVER_FEHLER" > "$RES/$TAG/STATUS"; stop_server; continue; fi
  fi
  # Rauchtest: 3 Items. Scheitert das (z. B. kein Chat-Template), lohnt der Rest nicht.
  $PY scripts/run_eval.py --api-base "http://127.0.0.1:$PORT/v1" --model-name "$TAG" --input-csv data/items/islamic_eval_dataset.csv --output-jsonl "$RES/$TAG/_smoke.jsonl" --max-items 3 --max-tokens "$MAXTOK" $(samp_args "$SAMP") > "$LOGS/smoke_$TAG.log" 2>&1
  if [ $? -ne 0 ]; then warn "Rauchtest $TAG fehlgeschlagen:"; tail -8 "$LOGS/smoke_$TAG.log"; warn "Haeufige Ursache: Modell ohne Chat-Template -> run_eval.py --system-prompt ... oder Template im Server setzen"; echo "RAUCHTEST_FEHLER" > "$RES/$TAG/STATUS"; stop_server; continue; fi
  $PY - "$RES/$TAG/_smoke.jsonl" <<'PYEOF'
import json,sys
for l in open(sys.argv[1],encoding="utf-8"):
    r=json.loads(l); print(f"   smoke {r['item_id']}: finish={r['finish_reason']} antwort={len(r['raw_response'])}z denken={r['reasoning_chars']}z offen={r['open_think']}")
    if r["finish_reason"]=="length": print("   [!] Smoke-Item lief ins Token-Limit (Schleife im Antworttext? Dann Sampling pruefen; sonst max_tokens erhoehen)")
PYEOF
  log "3/5 $TAG: Hadith/Koran/Fallen";  run_set "$TAG" islamic     data/items/islamic_eval_dataset.csv
  log "3/5 $TAG: Fara'id";               run_set "$TAG" faraid      data/items/faraid_eval_dataset.csv
  log "3/5 $TAG: Kalibrierset (nur Basislauf, fuer Phase B)"; run_set "$TAG" calibration data/items/calibration_set.csv
  echo "OK" > "$RES/$TAG/STATUS"; stop_server
done

# ---- 4. Statistik ----------------------------------------------------------
log "4/5 McNemar"
mcn() { # a b
  [ -f "$RES/$1/islamic.score.json" ] && [ -f "$RES/$2/islamic.score.json" ] || { warn "McNemar $1 vs $2 uebersprungen"; return; }
  for n in islamic faraid; do echo "--- $1 vs $2: $n"; $PY scripts/mcnemar_eval.py --file-a "$RES/$1/$n.score.json" --file-b "$RES/$2/$n.score.json" 2>&1 | tee "$RES/mcnemar_$1_vs_$2_$n.txt"; done
}
mcn qwen25-32b jais3-32b; mcn qwen3-30b-a3b jais3-mova

# ---- 5. Zusammenfassung + Paket zum Herunterladen --------------------------
log "5/5 Zusammenfassung"
$PY scripts/summarize.py --results "$RES"
OUT="phase_a_results_$(date +%Y%m%d_%H%M).tar.gz"; tar czf "$OUT" "$RES" "$LOGS" && echo -e "\n[+] Alles zum Herunterladen: $OUT"
