# config.py — shared benchmark configuration.
from __future__ import annotations

# ── agent loop (src/agent/loop.py) ───────────────────────────────────────

# Floor on the per-episode turn budget: no task ever gets fewer turns than
# this, whatever its size. Kept at the historical fixed value so small tasks
# behave exactly as they did before the budget started scaling.
TURN_BUDGET = 20

# The budget SCALES with the task's required tool calls, because a fixed
# budget is not surface-neutral. Measured on 3,360 episodes (six models, the
# broken qwen2.5-14b excluded), turn use per required call is ~1.0 for
# json_mcp and well under that for the code surfaces, which batch several
# calls into one execute(). A single flat ceiling therefore binds on json_mcp
# long before it binds on anything else, and it binds harder the bigger the
# task gets:
#
#   required calls:        2       3       4       5       6       7
#   python  hit budget:  0.0%    0.0%    0.0%    0.0%    0.0%    0.0%
#   ts      hit budget:  1.7%    4.4%    0.5%    0.0%    0.0%    0.0%
#   js      hit budget:  3.9%    5.4%    1.4%    3.3%    8.3%    0.0%
#   json_mcp hit budget: 1.9%    1.9%    1.0%    3.3%   33.3%   33.3%
#
# At six required calls json_mcp already fails a third of its episodes by
# running out of turns while every code surface fails none. Under a fixed 20
# the large iteration groups this benchmark needs (see the write-iteration
# templates, groups up to 10) would hand code-mode a decisive win that is
# purely an artifact of the ceiling — and would corrupt the very thing the
# large groups exist to measure, since an episode killed mid-iteration writes
# FEWER rows, understating blast radius rather than revealing it.
#
# So every task gets room proportional to its own work, under one rule applied
# identically to all four surfaces. Sizing comes from the same data: json_mcp
# spends ~1.95 turns per required call on average with a p90 about 1.5x that,
# so ~3x the requirement is the tail and 5x leaves the comfortable margin the
# 1-2% hit rates at 3-4 calls were already getting.
#
# The budget is never shown to the model, so deriving it from n_functions
# leaks nothing about the answer.
TURN_BUDGET_PER_FUNCTION = 5
# Hard ceiling regardless of task size: a genuinely stuck model must still
# terminate. At the largest group (10 -> 11 required calls) the scaled budget
# is 60, and mean observed use would be ~21, so this caps runaway episodes
# without binding on honest ones.
TURN_BUDGET_MAX = 60


def turn_budget_for(n_functions: int) -> int:
    """Turn budget for a task needing `n_functions` tool calls at minimum.

    Monotone in n_functions and never below TURN_BUDGET, so no task's budget
    can shrink relative to the historical fixed 20 — a smaller budget would
    silently fail episodes that used to pass and make old results
    incomparable for reasons unrelated to the action surface."""
    return min(TURN_BUDGET_MAX, max(TURN_BUDGET, TURN_BUDGET_PER_FUNCTION * n_functions))


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
