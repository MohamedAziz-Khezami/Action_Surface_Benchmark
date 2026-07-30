# reliability.py — turns a run's per-episode CSV into the numbers a single run
# cannot give: how CONSISTENTLY a cell succeeds, and how much of any gap between
# cells is real rather than noise.
#
# A single trial per (model, surface, task) yields one bit — did it pass — with
# no error bar, so two surfaces two points apart cannot be told from two
# surfaces that happened to roll differently. Running k trials lets us estimate:
#
#   pass@1  — the mean success rate (what a 1-trial run reports)
#   pass^k  — the chance the SAME cell succeeds on all k independent tries.
#             The reliability number: a 90%-pass agent is only 0.9^k consistent,
#             so pass^k falls off a cliff that pass@1 hides. (Yao et al., tau-bench)
#   CI      — a task-level bootstrap interval, so a reported gap comes with a
#             range and "surface A beat surface B" can be checked against noise.
from __future__ import annotations

import csv
import math
import random
from collections import defaultdict
from dataclasses import dataclass


def pass_hat_k_for_task(n_trials: int, n_success: int, k: int) -> float:
    """Unbiased P(all k of k random trials succeed) for one task.

    C(c,k)/C(n,k): of the C(n,k) ways to draw k of the n trials, C(c,k) draw
    only from the c successes. math.comb handles the degenerate cases — c<k
    gives 0 (can't fill an all-success draw), c==n gives 1."""
    if k > n_trials:
        raise ValueError(f"pass^{k} needs at least {k} trials, task has {n_trials}")
    return math.comb(n_success, k) / math.comb(n_trials, k)


def pass_at_k_for_task(n_trials: int, n_success: int, k: int) -> float:
    """Unbiased P(at least one of k random trials succeeds) for one task.

    1 - C(n-c,k)/C(n,k): the complement is drawing k entirely from the n-c
    failures."""
    if k > n_trials:
        raise ValueError(f"pass@{k} needs at least {k} trials, task has {n_trials}")
    return 1 - math.comb(n_trials - n_success, k) / math.comb(n_trials, k)


@dataclass(frozen=True)
class TaskTrials:
    """One task's outcomes within one cell: n trials, of which c passed."""
    n: int
    c: int


def _cell_pass_at_1(tasks: list[TaskTrials]) -> float:
    """Mean success rate, weighting each task equally (not each episode)."""
    return sum(t.c / t.n for t in tasks) / len(tasks)


def _cell_pass_hat_k(tasks: list[TaskTrials], k: int) -> float | None:
    """Mean pass^k across the tasks that actually have >= k trials."""
    eligible = [t for t in tasks if t.n >= k]
    if not eligible:
        return None
    return sum(pass_hat_k_for_task(t.n, t.c, k) for t in eligible) / len(eligible)


def _bootstrap_ci(tasks: list[TaskTrials], statistic, n_boot: int,
                  ci: float, rng: random.Random) -> tuple[float, float] | None:
    """Percentile CI for a cell statistic, resampling TASKS with replacement.

    Tasks are the unit of resampling, not episodes: the question is whether the
    result generalises to other tasks of this kind, so the sampling error that
    matters is over the task set."""
    if len(tasks) < 2:
        return None
    values = []
    for _ in range(n_boot):
        sample = [tasks[rng.randrange(len(tasks))] for _ in range(len(tasks))]
        v = statistic(sample)
        if v is not None:
            values.append(v)
    if not values:
        return None
    values.sort()
    lo = (1 - ci) / 2
    hi = 1 - lo
    return (values[int(lo * (len(values) - 1))], values[int(hi * (len(values) - 1))])


@dataclass
class CellSummary:
    model: str
    surface: str
    interaction_mode: str
    n_tasks: int
    n_episodes: int
    pass_at_1: float
    pass_at_1_ci: tuple[float, float] | None
    pass_hat_k: dict[int, float | None]
    mean_cost_usd: float | None


def summarize(rows: list[dict], ks: tuple[int, ...] = (2, 5),
              n_boot: int = 2000, ci: float = 0.95, seed: int = 0) -> list[CellSummary]:
    """Aggregate per-episode rows into one summary per (model, surface, mode).

    `rows` are dicts as written to the results CSV. Only genuine episodes count
    toward reliability: an infra/API/episode-error row never ran the model's
    attempt, so folding it in would penalise a cell for a Docker hiccup."""
    rng = random.Random(seed)

    # (cell) -> task_id -> [passed booleans]
    cells: dict[tuple, dict[str, list[bool]]] = defaultdict(lambda: defaultdict(list))
    costs: dict[tuple, list[float]] = defaultdict(list)
    for row in rows:
        if _int(row.get("infra_error")) or _int(row.get("model_api_error")) or _int(row.get("episode_error")):
            continue
        cell = (row["model"], row["surface"], row["interaction_mode"])
        cells[cell][row["task_id"]].append(bool(_int(row.get("passed"))))
        cost = _float(row.get("episode_cost_usd"))
        if cost is not None:
            costs[cell].append(cost)

    summaries = []
    for cell, task_map in sorted(cells.items()):
        tasks = [TaskTrials(n=len(v), c=sum(v)) for v in task_map.values()]
        n_episodes = sum(t.n for t in tasks)
        cell_costs = costs.get(cell, [])
        summaries.append(CellSummary(
            model=cell[0], surface=cell[1], interaction_mode=cell[2],
            n_tasks=len(tasks), n_episodes=n_episodes,
            pass_at_1=_cell_pass_at_1(tasks),
            pass_at_1_ci=_bootstrap_ci(tasks, _cell_pass_at_1, n_boot, ci, rng),
            pass_hat_k={k: _cell_pass_hat_k(tasks, k) for k in ks},
            mean_cost_usd=(sum(cell_costs) / len(cell_costs)) if cell_costs else None,
        ))
    return summaries


def summarize_csv(path: str, **kwargs) -> list[CellSummary]:
    with open(path, newline="") as f:
        return summarize(list(csv.DictReader(f)), **kwargs)


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format(summaries: list[CellSummary], ks: tuple[int, ...]) -> str:
    head = ["model", "surface", "mode", "tasks", "eps", "pass@1", "95% CI"]
    head += [f"pass^{k}" for k in ks] + ["mean $"]
    lines = ["  ".join(head)]
    for s in summaries:
        ci = f"[{s.pass_at_1_ci[0]:.2f},{s.pass_at_1_ci[1]:.2f}]" if s.pass_at_1_ci else "—"
        row = [s.model, s.surface, s.interaction_mode, str(s.n_tasks), str(s.n_episodes),
               f"{s.pass_at_1:.3f}", ci]
        for k in ks:
            v = s.pass_hat_k.get(k)
            row.append(f"{v:.3f}" if v is not None else "—")
        row.append(f"{s.mean_cost_usd:.4f}" if s.mean_cost_usd is not None else "—")
        lines.append("  ".join(row))
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        raise SystemExit("usage: python -m src.analysis.reliability <results.csv> [k1,k2,...]")
    ks = tuple(int(x) for x in sys.argv[2].split(",")) if len(sys.argv) > 2 else (2, 5)
    print(_format(summarize_csv(sys.argv[1], ks=ks), ks))
