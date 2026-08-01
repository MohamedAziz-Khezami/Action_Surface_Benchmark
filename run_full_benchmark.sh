#!/usr/bin/env bash
# run_full_benchmark.sh — runs the full benchmark against every model in
# models.yaml, one at a time: starts that model's llama-server, waits until
# it's actually ready to serve (polls /v1/models rather than a fixed sleep,
# since load time varies enormously by model size — 12B loads in a couple
# minutes, 72B split across two files can take much longer, especially on
# a cold cache), runs the full benchmark against it, then stops that
# llama-server before moving to the next model. Never runs two models'
# servers at once, since several of these are close to the workstation's
# VRAM ceiling on their own.
#
# Usage: ./run_full_benchmark.sh [difficulty]
#   difficulty defaults to "all" (every tier). Pass "easy", "medium", "hard",
#   or "expert" to restrict to one tier instead.
#
# Requires: llama-server on PATH, python3 with this repo's deps installed,
# and enough disk for whichever models aren't already cached under
# ~/.cache/huggingface/hub/.
set -uo pipefail  # deliberately not -e: one model failing must not abort the rest

DIFFICULTY="${1:-all}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

READY_TIMEOUT_S="${READY_TIMEOUT_S:-3600}"   # 1 hour ceiling per model — covers a cold, first-time 110GB download
READY_POLL_INTERVAL_S=5
SHUTDOWN_TIMEOUT_S=30

# ── context window ───────────────────────────────────────────────────────
# llama-server defaults to a small total context SPLIT ACROSS PARALLEL SLOTS
# (n_ctx_slot = 4096 with the default 4 slots). That is far too small here:
# the system prompt + tool catalog alone is ~12k tokens for the code surfaces
# and ~17k for TypeScript, so every request 400s with "exceeds the available
# context size" before the model does any work — and when a request squeaks in
# but generation runs out mid-tool-call, the harness gets truncated JSON
# ("Unterminated string ...") instead of a clean error.
#
# So: pin an explicit context and give it to ONE slot. The harness issues one
# request at a time, so extra slots buy nothing and only divide the window.
CTX_SIZE="${CTX_SIZE:-32768}"   # covers the heaviest prompt + a full 20-turn conversation
PARALLEL_SLOTS=1

# Every model gets the SAME context. That is deliberate: this benchmark holds
# everything but the action surface constant, so giving one model a different
# window than the others would introduce exactly the kind of confound the
# design exists to avoid.
#
# Sizing (target box: 4x RTX 5090 = 128GB VRAM): the whole fleet fits at its
# pinned precision with a 32k window — the heaviest, Qwen2.5-72B-Q8, needs
# ~76GB of weights plus ~10GB of KV cache, leaving ample headroom. On a smaller
# box, lower it globally rather than per-model, e.g.
#   CTX_SIZE=16384 ./run_full_benchmark.sh
# so every model still runs under identical conditions.
#
# A case statement (rather than an associative array) is used below so a
# per-model exception, if one ever becomes unavoidable, still works on bash 3.2
# — macOS's system bash, which has no `declare -A`.
ctx_for_model() {
    case "$1" in
        *) echo "$CTX_SIZE" ;;
    esac
}

CURRENT_PID=""

# Ensure a still-running server gets killed even if the script is
# interrupted (Ctrl+C) or exits early on an unexpected error.
cleanup() {
    if [[ -n "$CURRENT_PID" ]] && kill -0 "$CURRENT_PID" 2>/dev/null; then
        echo "[cleanup] stopping still-running llama-server (pid $CURRENT_PID)"
        kill "$CURRENT_PID" 2>/dev/null
        wait "$CURRENT_PID" 2>/dev/null
    fi
}
trap cleanup EXIT INT TERM

# One line per model: "name|model_id|port" — model_id is "repo:file" or
# a bare "repo" (no colon) for the rare entry with no specific file to pin.
# Read directly from models.yaml so this script can never drift from the
# actual registry.
mapfile -t MODEL_LINES < <(python3 -c "
import yaml
data = yaml.safe_load(open('models.yaml'))
for m in data['models']:
    port = m['base_url'].rsplit(':', 1)[1].split('/')[0]
    print(f\"{m['name']}|{m['model_id']}|{port}\")
")

if [[ ${#MODEL_LINES[@]} -eq 0 ]]; then
    echo "no models found in models.yaml" >&2
    exit 1
fi

echo "found ${#MODEL_LINES[@]} model(s) in models.yaml, difficulty=${DIFFICULTY}"
echo

for line in "${MODEL_LINES[@]}"; do
    IFS='|' read -r NAME MODEL_ID PORT <<< "$line"

    if [[ "$MODEL_ID" == *:* ]]; then
        HF_REPO="${MODEL_ID%%:*}"
        HF_FILE="${MODEL_ID#*:}"
    else
        HF_REPO="$MODEL_ID"
        HF_FILE=""
    fi

    OUT_DIR="results/${NAME}"
    mkdir -p "$OUT_DIR"
    SERVER_LOG="${OUT_DIR}/llama-server.log"

    MODEL_CTX="$(ctx_for_model "$NAME")"

    echo "════════════════════════════════════════════════════════════════"
    echo "[$NAME] starting llama-server on port ${PORT}"
    echo "[$NAME]   repo: ${HF_REPO}"
    [[ -n "$HF_FILE" ]] && echo "[$NAME]   file: ${HF_FILE}"
    echo "[$NAME]   ctx:  ${MODEL_CTX} tokens across ${PARALLEL_SLOTS} slot(s)"
    echo "[$NAME]   log:  ${SERVER_LOG}"

    if [[ -n "$HF_FILE" ]]; then
        nohup llama-server --hf-repo "$HF_REPO" --hf-file "$HF_FILE" \
            --port "$PORT" --jinja -ngl 999 \
            -c "$MODEL_CTX" -np "$PARALLEL_SLOTS" > "$SERVER_LOG" 2>&1 &
    else
        nohup llama-server --hf-repo "$HF_REPO" \
            --port "$PORT" --jinja -ngl 999 \
            -c "$MODEL_CTX" -np "$PARALLEL_SLOTS" > "$SERVER_LOG" 2>&1 &
    fi
    CURRENT_PID=$!
    echo "[$NAME] pid: ${CURRENT_PID}"

    # Poll /v1/models instead of a fixed sleep — a large model's first-time
    # download+load can take anywhere from a couple minutes to the better
    # part of an hour; a blind sleep would either waste time on small models
    # or fire the benchmark too early against a not-yet-ready server (every
    # episode would fail with connection-refused).
    echo "[$NAME] waiting for it to become ready (up to ${READY_TIMEOUT_S}s)..."
    ELAPSED=0
    READY=0
    while [[ $ELAPSED -lt $READY_TIMEOUT_S ]]; do
        if ! kill -0 "$CURRENT_PID" 2>/dev/null; then
            echo "[$NAME] llama-server exited during startup — check ${SERVER_LOG}" >&2
            break
        fi
        if curl -s -o /dev/null -m 3 "http://localhost:${PORT}/v1/models"; then
            READY=1
            break
        fi
        sleep "$READY_POLL_INTERVAL_S"
        ELAPSED=$((ELAPSED + READY_POLL_INTERVAL_S))
    done

    if [[ $READY -ne 1 ]]; then
        echo "[$NAME] SKIPPING — never became ready within ${READY_TIMEOUT_S}s (or crashed on startup)" >&2
        kill "$CURRENT_PID" 2>/dev/null
        wait "$CURRENT_PID" 2>/dev/null
        CURRENT_PID=""
        echo
        continue
    fi
    echo "[$NAME] ready after ~${ELAPSED}s"

    echo "[$NAME] running full benchmark (difficulty=${DIFFICULTY})..."
    python3 main.py run --models "$NAME" --difficulty "$DIFFICULTY" \
        --out "${OUT_DIR}/${NAME}.csv"
    RUN_STATUS=$?
    if [[ $RUN_STATUS -ne 0 ]]; then
        echo "[$NAME] benchmark run exited with status ${RUN_STATUS} — see output above" >&2
    else
        echo "[$NAME] benchmark complete: ${OUT_DIR}/${NAME}.csv"
    fi

    echo "[$NAME] stopping llama-server (pid ${CURRENT_PID})"
    kill "$CURRENT_PID" 2>/dev/null
    STOP_ELAPSED=0
    while kill -0 "$CURRENT_PID" 2>/dev/null && [[ $STOP_ELAPSED -lt $SHUTDOWN_TIMEOUT_S ]]; do
        sleep 1
        STOP_ELAPSED=$((STOP_ELAPSED + 1))
    done
    if kill -0 "$CURRENT_PID" 2>/dev/null; then
        echo "[$NAME] still running after ${SHUTDOWN_TIMEOUT_S}s, force-killing"
        kill -9 "$CURRENT_PID" 2>/dev/null
    fi
    wait "$CURRENT_PID" 2>/dev/null
    CURRENT_PID=""
    echo "[$NAME] stopped, VRAM freed"
    echo
done

echo "════════════════════════════════════════════════════════════════"
echo "all models done — results under results/<model_name>/<model_name>.csv"
