# test_reliability.py — the pass^k / pass@k estimators decide how the headline
# reliability numbers read, so their arithmetic is pinned against hand values.
from __future__ import annotations

import pytest

from src.analysis import reliability as R


# ── the per-task estimators ─────────────────────────────────────────────────

def test_pass_hat_k_all_success_is_one():
    assert R.pass_hat_k_for_task(n_trials=5, n_success=5, k=3) == 1.0


def test_pass_hat_k_too_few_successes_is_zero():
    # only 2 successes, cannot fill an all-3-succeed draw
    assert R.pass_hat_k_for_task(n_trials=5, n_success=2, k=3) == 0.0


def test_pass_hat_k_half_and_half():
    # n=4, c=2, k=2: C(2,2)/C(4,2) = 1/6
    assert R.pass_hat_k_for_task(4, 2, 2) == pytest.approx(1 / 6)


def test_pass_hat_1_equals_success_rate():
    assert R.pass_hat_k_for_task(10, 7, 1) == pytest.approx(0.7)


def test_pass_at_k_is_one_when_any_success_guaranteed():
    # n=5, c=4: drawing 2 all-failures is impossible (only 1 failure) -> 1.0
    assert R.pass_at_k_for_task(5, 4, 2) == 1.0


def test_pass_at_k_half_and_half():
    # n=4, c=2, k=2: 1 - C(2,2)/C(4,2) = 1 - 1/6 = 5/6
    assert R.pass_at_k_for_task(4, 2, 2) == pytest.approx(5 / 6)


def test_pass_hat_k_decays_below_pass_at_1():
    # the whole point: consistency is lower than average success
    import math
    n, c = 8, 6                      # 75% pass@1
    assert R.pass_hat_k_for_task(n, c, 1) == pytest.approx(0.75)
    p4 = R.pass_hat_k_for_task(n, c, 4)
    assert p4 < 0.75
    assert p4 == pytest.approx(math.comb(6, 4) / math.comb(8, 4))   # 15/70


def test_k_greater_than_trials_raises():
    with pytest.raises(ValueError):
        R.pass_hat_k_for_task(n_trials=2, n_success=2, k=3)


# ── cell aggregation and CSV summary ────────────────────────────────────────

def _rows(specs):
    """specs: list of (model, surface, task_id, passed[, cost])."""
    out = []
    for i, spec in enumerate(specs):
        model, surface, task, passed = spec[:4]
        cost = spec[4] if len(spec) > 4 else ""
        out.append({
            "episode_id": f"e{i}", "model": model, "surface": surface,
            "interaction_mode": "tool_call", "task_id": task,
            "passed": str(passed), "episode_cost_usd": cost,
            "infra_error": "0", "model_api_error": "0", "episode_error": "0",
        })
    return out


def test_summary_pass_at_1_weights_tasks_equally():
    # task A: 2/2 pass, task B: 0/2 pass -> pass@1 = mean(1.0, 0.0) = 0.5
    rows = _rows([("m", "python", "A", 1), ("m", "python", "A", 1),
                  ("m", "python", "B", 0), ("m", "python", "B", 0)])
    (s,) = R.summarize(rows, ks=(2,), n_boot=100)
    assert s.n_tasks == 2 and s.n_episodes == 4
    assert s.pass_at_1 == pytest.approx(0.5)
    # task A always passes (pass^2=1), task B never (pass^2=0) -> mean 0.5
    assert s.pass_hat_k[2] == pytest.approx(0.5)


def test_summary_separates_cells():
    rows = _rows([("m", "python", "A", 1), ("m", "json_mcp", "A", 0)])
    out = {(s.surface): s for s in R.summarize(rows, ks=(1,), n_boot=50)}
    assert out["python"].pass_at_1 == 1.0
    assert out["json_mcp"].pass_at_1 == 0.0


def test_error_episodes_are_excluded():
    rows = _rows([("m", "python", "A", 1)])
    rows.append({**rows[0], "episode_id": "bad", "passed": "0", "infra_error": "1"})
    (s,) = R.summarize(rows, ks=(1,), n_boot=50)
    # the infra-error row must not drag the rate down
    assert s.n_episodes == 1 and s.pass_at_1 == 1.0


def test_mean_cost_ignores_blank_cost():
    rows = _rows([("m", "python", "A", 1, "0.10"), ("m", "python", "B", 1, "")])
    (s,) = R.summarize(rows, ks=(1,), n_boot=50)
    assert s.mean_cost_usd == pytest.approx(0.10)


def test_bootstrap_ci_brackets_the_point_estimate():
    rows = _rows([("m", "python", t, p) for t, p in
                  [("A", 1), ("B", 1), ("C", 1), ("D", 0), ("E", 0), ("F", 0)]])
    (s,) = R.summarize(rows, ks=(1,), n_boot=2000, seed=1)
    lo, hi = s.pass_at_1_ci
    assert lo <= s.pass_at_1 <= hi
    assert 0.0 <= lo <= hi <= 1.0
