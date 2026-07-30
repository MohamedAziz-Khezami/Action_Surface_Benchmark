# cli.py — argument parsing for main.py.
from __future__ import annotations

import argparse

from config import DEFAULT_DIFFICULTY, DEFAULT_MODELS_YAML, DEFAULT_SURFACES, SEED_BASE, TASKS_PER_TIER


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="run episodes against the frozen task corpus")
    run_parser.add_argument("--models", required=True, help="comma-separated model names from models.yaml")
    run_parser.add_argument("--surfaces", default=DEFAULT_SURFACES,
                             help="comma-separated: python,js,ts,json_mcp")
    run_parser.add_argument("--interaction-modes", default=None,
                             help='comma-separated: tool_call,text_block. '
                                  "Default: tool_call for models with supports_tool_calling, else text_block.")
    run_parser.add_argument("--difficulty", default=DEFAULT_DIFFICULTY, help="easy,medium,hard,expert,all")
    run_parser.add_argument("--limit", type=int, default=None, help="max tasks per difficulty tier")
    run_parser.add_argument("--n-trials", type=int, default=1,
                             help="independent episodes per (model, surface, mode, task). "
                                  "Reliability metrics (pass^k) need k<=n-trials repeats to "
                                  "estimate how consistently a cell succeeds, not just whether "
                                  "it ever does. Default 1.")
    run_parser.add_argument("--models-yaml", default=DEFAULT_MODELS_YAML)
    run_parser.add_argument("--out", default=None)

    tools_parser = subparsers.add_parser(
        "gen-tools",
        help="regenerate every surface's tool documentation from the tool-server")
    tools_parser.add_argument(
        "--check", action="store_true",
        help="don't write anything: exit non-zero if any generated file is out of "
             "date. Use in CI to catch a hand-edited tool document, which would "
             "silently give one surface different information from the others.")

    gen_parser = subparsers.add_parser("generate-tasks", help="freeze/refresh the task corpus")
    gen_parser.add_argument("--n-per-tier", type=int, default=TASKS_PER_TIER,
                             help=f"tasks to generate per difficulty tier (default: {TASKS_PER_TIER})")
    gen_parser.add_argument("--seed-base", type=int, default=SEED_BASE,
                             help=f"first task's seed; each subsequent task increments by 1 "
                                  f"(default: {SEED_BASE}). Same seed_base + n_per_tier always "
                                  "reproduces the identical corpus; change it to generate a different one.")

    return parser.parse_args(argv)
