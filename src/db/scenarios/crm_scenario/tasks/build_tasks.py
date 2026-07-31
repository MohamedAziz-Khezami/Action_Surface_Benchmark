# build_tasks.py — freezes the task corpus. Each task is a PAIR of
# artifacts: task_XXX.json (the contract) + task_XXX.sqlite (the exact world
# it runs against, built once here and never rebuilt at episode time — so
# reproducibility doesn't depend on generator code staying frozen).
from __future__ import annotations

import importlib
import json
import random
from pathlib import Path

from config import SEED_BASE, TASKS_PER_TIER, TIERS  # re-exported: existing importers of these names are unchanged
from src.db.scenarios.crm_scenario.tasks import template_interpreter as ti
from src.db.scenarios.crm_scenario.tasks import world_builder as wb

TASKS_DIR = Path(__file__).parent
FROZEN_DIR = TASKS_DIR / "frozen"

def build_all(n_per_tier: int = TASKS_PER_TIER, seed_base: int = SEED_BASE, verbose: bool = True) -> int:
    menus = ti.load_actions()
    idx, total = 0, 0
    for tier in TIERS:
        cfg = importlib.import_module(f".tiers.{tier}", package=__package__).TIER_CONFIG
        out_dir = FROZEN_DIR / tier
        out_dir.mkdir(parents=True, exist_ok=True)
        #Delete old stale files for a new fresh tasks build
        for stale in list(out_dir.glob("task_*.json")) + list(out_dir.glob("task_*.sqlite")):
            stale.unlink()

        # Balanced, deterministic template assignment: every registered
        # template appears (near-)equally often, so none is left with zero
        # frozen instances as a tier's template count grows toward n_per_tier.
        # A plain per-task random.choice() left some templates unsampled once a
        # tier held enough of them; a shuffled round-robin guarantees coverage.
        templates = cfg["templates"]
        assignment = (templates * (n_per_tier // len(templates) + 1))[:n_per_tier]
        random.Random(f"{tier}:template-assignment:{n_per_tier}").shuffle(assignment)

        for j in range(n_per_tier):
            task_seed = seed_base + idx
            template_name = assignment[j]
            template = ti.load_template(template_name, tier)
            task_id = f"task_{idx:03d}"
            task = wb.build_task(task_seed, template, out_dir / f"{task_id}.sqlite", menus)

            task.update({"task_id": task_id, "world_seed": task_seed,
                          "difficulty": tier, "template": template_name,
                          "pattern": template["pattern"]})

            (out_dir / f"{task_id}.json").write_text(
                json.dumps(task, indent=2), encoding="utf-8")
            idx += 1
            total += 1
        if verbose:
            print(f"[build] {tier}: {n_per_tier} task+world pairs written to {out_dir}")
    return total


def load_tasks(selector: str = "all") -> list[dict]:
    """Load frozen instances. Selector: 'all' | 'easy' | 'medium' | 'hard' | 'expert'.
    Each task dict gets a runtime-only 'world_db' path to its frozen world
    (not stored in the JSON itself)."""
    wanted = TIERS if selector == "all" else (selector,)
    out = []
    for tier in wanted:
        for f in sorted((FROZEN_DIR / tier).glob("*.json")):
            task = json.loads(f.read_text(encoding="utf-8"))
            task["world_db"] = str(f.with_suffix(".sqlite"))
            out.append(task)
    return out


if __name__ == "__main__":
    n = build_all()
    print(f"[build] total: {n} task+world pairs frozen under {FROZEN_DIR}")
