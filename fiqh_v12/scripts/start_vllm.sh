#!/bin/bash
# Aufruf:  bash start_vllm.sh /workspace/models/Jais-3-MoVA-36B-A4B
#          bash start_vllm.sh /workspace/models/Qwen3-30B-A3B
# Beendet einen laufenden vLLM, startet neu mit 16384 Kontext und wartet bis der Server antwortet.
MODEL="$1"
[ -z "$MODEL" ] && { echo "Modellpfad fehlt"; exit 1; }
pkill -f "vllm serve" 2>/dev/null; pkill -f "vllm.entrypoints" 2>/dev/null; sleep 8
cd /workspace
nohup vllm serve "$MODEL" --port 8000 --max-model-len 16384 --trust-remote-code --gpu-memory-utilization 0.90 > /workspace/vllm_$(basename "$MODEL").log 2>&1 &
echo "vLLM startet fuer $MODEL ..."
for i in $(seq 1 120); do
  if curl -s localhost:8000/v1/models | grep -q '"id"'; then echo "Server bereit nach $((i*5))s"; curl -s localhost:8000/v1/models | head -c 300; echo; exit 0; fi
  sleep 5
done
echo "Server kam nicht hoch - Log:"; tail -30 /workspace/vllm_$(basename "$MODEL").log; exit 1
