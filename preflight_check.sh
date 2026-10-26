#!/usr/bin/env bash
# ==============================================================================
# Pre-Flight Environment Check: Pod Hardware & Software Stack
# Prüft: GPU, VRAM, CUDA, PyTorch, FlashAttention, vLLM & Kern-Abhängigkeiten
# ==============================================================================

set -eo pipefail

RED="\033[1;31m"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
BLUE="\033[1;34m"
NC="\033[0m"

log_info() { echo -e "${BLUE}[*] $1${NC}"; }
log_ok()   { echo -e "  ${GREEN}[+] $1${NC}"; }
log_warn() { echo -e "  ${YELLOW}[!] $1${NC}"; }
log_fail() { echo -e "  ${RED}[X] $1${NC}"; exit 1; }

echo "=================================================================="
echo " RUNPOD / CLOUD POD PRE-FLIGHT ENVIRONMENT CHECK"
echo "=================================================================="

# 1. GPU & Treiber-Erkennung
log_info "1. Prüfe NVIDIA Treiber & GPU-Hardware..."
if ! command -v nvidia-smi >/dev/null 2>&1; then
    log_fail "nvidia-smi nicht gefunden. Keine NVIDIA-Treiber geladen!"
fi

GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -n 1)
TOTAL_VRAM_MIB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -n 1)
DRIVER_VERSION=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -n 1)

log_ok "GPU erkannt:      ${GPU_NAME}"
log_ok "Treiber-Version:  ${DRIVER_VERSION}"
log_ok "VRAM Total:       ${TOTAL_VRAM_MIB} MiB"

# Mindest-VRAM Check für 30B/32B BF16 Inferenz (~80 GB = ~80.000 MiB)
if [ "${TOTAL_VRAM_MIB}" -lt 75000 ]; then
    log_warn "VRAM unter 75 GB (${TOTAL_VRAM_MIB} MiB). Für BF16 Single-GPU (H100/H200) knapp!"
else
    log_ok "VRAM-Dimensionierung ausreichend für BF16 Single-GPU."
fi

# 2. Python-Umgebung
log_info "2. Prüfe Python-Version & Interpreter..."
PYTHON_BIN=$(command -v python3 || command -v python || true)
if [ -z "${PYTHON_BIN}" ]; then
    log_fail "Kein Python-Interpreter im PATH gefunden!"
fi
PY_VER=$(${PYTHON_BIN} -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
log_ok "Python Interpreter: ${PYTHON_BIN} (v${PY_VER})"

# 3. PyTorch & CUDA Toolkit
log_info "3. Prüfe PyTorch & CUDA-Anbindung..."
${PYTHON_BIN} -c "
import sys, torch
if not torch.cuda.is_available():
    print('Torch meldet: CUDA ist NICHT verfuegbar!', file=sys.stderr)
    sys.exit(1)
print(f'PyTorch Version: {torch.__version__}')
print(f'PyTorch CUDA Build: {torch.version.cuda}')
print(f'Geraet 0: {torch.cuda.get_device_name(0)}')
cap = torch.cuda.get_device_capability(0)
print(f'Compute Capability: {cap[0]}.{cap[1]}')
" || log_fail "PyTorch CUDA-Check fehlgeschlagen!"
log_ok "PyTorch CUDA-Zugriff intakt."

# 4. FlashAttention / vLLM-Backend
log_info "4. Prüfe FlashAttention & vLLM Serving Stack..."
${PYTHON_BIN} -c "
import sys
# vLLM Check
try:
    import vllm
    print(f'vLLM Version: {vllm.__version__}')
except ImportError:
    print('FEHLER: vLLM ist nicht installiert!', file=sys.stderr)
    sys.exit(1)

# FlashAttention Check
try:
    import flash_attn
    print(f'flash-attn Version: {flash_attn.__version__}')
except ImportError:
    print('HINWEIS: flash-attn Python-Paket nicht direkt importierbar (vLLM nutzt ggf. eigene Kernels/FlashInfer).')
" || log_fail "vLLM-Paket fehlt!"
log_ok "Inferenz-Stack bereit."

# 5. Wissenschaftliche & Evaluierungs-Module
log_info "5. Prüfe Evaluierungs- und Statistik-Abhängigkeiten..."
REQUIRED_PKGS=("transformers:transformers" "scipy:scipy" "sklearn:scikit-learn" "tabulate:tabulate" "matplotlib:matplotlib" "pandas:pandas" "requests:requests")  # import-Name:pip-Name (pip install sklearn schlaegt fehl!)
MISSING_PKGS=()

for spec in "${REQUIRED_PKGS[@]}"; do
    mod="${spec%%:*}"; pipname="${spec##*:}"
    if ! ${PYTHON_BIN} -c "import ${mod}" >/dev/null 2>&1; then
        MISSING_PKGS+=("${pipname}")
    fi
done

if [ ${#MISSING_PKGS[@]} -ne 0 ]; then
    log_warn "Fehlende Pakete: ${MISSING_PKGS[*]}"
    log_info "Installiere fehlende Pakete via pip..."
    pip install --no-cache-dir "${MISSING_PKGS[@]}"
    log_ok "Abhängigkeiten nachinstalliert."
else
    log_ok "Alle Kernpakete vorhanden."
fi

# 6. Dateisystem- & Speicher-Check (Containerdisk)
log_info "6. Prüfe Container-Speicherplatz (NVMe)..."
DISK_PATH="${DISK_PATH:-$([ -d /workspace ] && echo /workspace || echo /)}"   # Modelle/HF-Cache liegen auf dem Volume, nicht auf /
FREE_DISK_GB=$(df -BG "${DISK_PATH}" | awk 'NR==2 {print $4}' | sed 's/G//')
log_ok "Freier Speicherplatz auf ${DISK_PATH}: ${FREE_DISK_GB} GB"
if [ "${FREE_DISK_GB}" -lt 160 ]; then
    log_warn "Weniger als 160 GB frei: zwei 30B-Modelle in bf16 (je ~60-65 GB) + Cache brauchen ~150 GB."
fi

# 7. Netz: Modell-Downloads und Daten-Bootstrap
log_info "7. Prüfe Netzzugang (Hugging Face, GitHub)..."
for url in https://huggingface.co https://github.com; do
    code=$(curl -s -o /dev/null -m 15 -w "%{http_code}" "$url" || true)
    case "$code" in 2*|3*|401|403) log_ok "$url erreichbar (HTTP $code)";; *) log_warn "$url NICHT erreichbar (HTTP ${code:-000})";; esac
done
GPU_COUNT=$(nvidia-smi --query-gpu=name --format=csv,noheader | wc -l)
log_ok "Anzahl GPUs: ${GPU_COUNT} (beide Modelle gleichzeitig nur ab 2 GPUs; auf 1 GPU nacheinander fahren)"

echo "=================================================================="
echo -e "${GREEN}ALLE SYSTEM-CHECKS ERFOLGREICH BESTANDEN. POD IST EINSATZBEREIT.${NC}"
echo "=================================================================="