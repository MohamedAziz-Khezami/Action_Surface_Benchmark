# config.py — shared benchmark configuration.
from __future__ import annotations

# ── agent loop (src/agent/loop.py) ───────────────────────────────────────

TURN_BUDGET = 20


# ── cost accounting (src/meter/meter.py) ─────────────────────────────────
# Cost is the dependent variable of the code-vs-MCP question: code-mode's
# whole claim is that it does the same work for fewer tokens. But it does not
# make the work free — it moves it out of the token stream and into executed
# code, i.e. into sandbox compute. Pricing only tokens would credit code-mode
# for the tokens it saves while ignoring the compute it spends, overstating its
# advantage. So the sandbox second is priced too.
#
# This is a placeholder rate, deliberately kept here as one editable knob so a
# reader can re-derive every cost figure under their own assumptions rather than
# trusting ours. Default ≈ one cloud vCPU-second (AWS Fargate on-demand,
# ~$0.04048 per vCPU-hour ÷ 3600). Per-model token prices live in models.yaml.
SANDBOX_USD_PER_SECOND = 0.04048 / 3600


TRAJECTORY_DIR = "results/trajectories"

# Retry backoff (seconds) for a momentarily-unreachable container.
RETRY_DELAYS_S = (0.5, 1.0, 2.0)

# HTTP request timeouts (seconds)
EXEC_HTTP_TIMEOUT_S = 60        # code-mode execute() call to the executor container
TOOL_CALL_HTTP_TIMEOUT_S = 30   # json_mcp direct tool-server call

# Ceiling on ONE model turn. The OpenAI SDK defaults to 600s, which is far too
# generous here: a local model that stops emitting (no stop token, a decode
# loop) would burn 10 minutes per turn, and with a 20-turn budget that is over
# three hours for a single episode — enough to stall an unattended fleet run.
# A legitimate turn, even for the 72B at Q8 with a long prompt, lands well
# under two minutes, so this leaves ample headroom while capping a hang. When
# it fires the harness records a model_api_error and moves on, which is the
# honest outcome: the model failed to answer in reasonable time.
MODEL_REQUEST_TIMEOUT_S = 300

# Consecutive model-API failures after which a model is abandoned for the rest
# of the run. A per-turn timeout caps ONE stuck request, but does nothing about
# a server that has stopped serving entirely: the harness will happily feed a
# dead llama-server every remaining episode, each costing a full timeout. That
# happened — a CUDA context died while the process stayed up answering HTTP,
# and the run spent 37 hours producing nothing but timeouts.
#
# A model that is genuinely working never fails this many times in a row, so
# the threshold trades a bounded detection cost (5 x MODEL_REQUEST_TIMEOUT_S,
# ~25 minutes) for the certainty that a wedged server cannot consume the rest
# of the run. Remaining episodes for that model are left unwritten rather than
# recorded as failures — they were never attempted, and scoring them would
# understate the model.
CONSECUTIVE_API_ERROR_LIMIT = 5

# ── Docker orchestration (src/docker_runner/episode.py) ──────────────────
CONTAINER_READY_TIMEOUT_S = 15.0        # max wait for a container to answer /health or /openapi.json
CONTAINER_READY_POLL_INTERVAL_S = 0.3
CONTAINER_READY_REQUEST_TIMEOUT_S = 1.0

TOOL_SERVER_IMAGE = "action-surface-bench/tool-server"
EXECUTOR_IMAGES = {
    "python": "action-surface-bench/python-executor",
    "js": "action-surface-bench/js-executor",
    "ts": "action-surface-bench/ts-executor",
}

# ── task generation (build_tasks.py / crm_db.py / world_builder.py) ──────
SEED_BASE = 1000
# 60 per tier so that, under the balanced round-robin assignment in
# build_tasks.py, each of a tier's ~8-10 templates lands ~6 instances — enough
# per template for the per-cell statistics (pass^k etc.) to mean something,
# rather than 1-2 instances that are really "one task with error bars".
TASKS_PER_TIER = 60
TIERS = ("easy", "medium", "hard", "expert")

SIM_TODAY = "2026-06-01"  # frozen simulation clock every frozen task/world uses

# Background (noise) row counts per table, injected alongside each task's
# own kernel rows — same distribution regardless of task/tier.
BACKGROUND_COUNTS = {"reps": 6, "contacts": 60, "leads": 40, "deals": 35,
                      "activities": 50, "followups": 15}
GUARD_REDRAW_LIMIT = 30  # max redraw attempts before a guard-violating background row gives up

# ── CLI defaults (cli.py) ─────────────────────────────────────────────────
DEFAULT_MODELS_YAML = "models.yaml"
DEFAULT_DIFFICULTY = "easy"
DEFAULT_SURFACES = "python,js,ts,json_mcp"
