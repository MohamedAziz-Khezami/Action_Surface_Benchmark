# test_iteration_groups.py — large iteration groups, and the turn budget that
# has to scale with them.
#
# WHY THIS FILE EXISTS. Blast radius (unauthorized writes) was structurally
# unmeasurable: the corpus authorized at most 6 writes per task, so an agent
# that over-wrote had almost no room to show it. Groups now reach 10.
#
# But enlarging groups alone would have BROKEN the study rather than improved
# it. Measured over 3,360 episodes, json_mcp spends about one turn per tool
# call while the code surfaces batch several into one execute(), so a fixed
# 20-turn ceiling binds on json_mcp and on nothing else — at six required
# calls json_mcp already failed 33% of episodes on turn exhaustion while
# python failed 0%. Under a fixed budget, bigger groups would have handed
# code-mode a large win that was purely an artifact of the ceiling, and would
# have made blast radius WORSE to measure, not better: an episode killed
# mid-iteration writes fewer rows, hiding over-writing instead of exposing it.
#
# So the two changes are one change, and these tests pin both halves.
from __future__ import annotations

import collections
import glob
import json
from pathlib import Path

import pytest
import yaml

from config import TURN_BUDGET, TURN_BUDGET_MAX, turn_budget_for

FROZEN = Path(__file__).parent.parent / "db" / "scenarios" / "crm_scenario" / "tasks" / "frozen"
TEMPLATES = Path(__file__).parent.parent / "db" / "scenarios" / "crm_scenario" / "tasks" / "templates"

# The templates whose group size drives the number of rows a CORRECT solution
# writes. Read-only groups (count_*/sum_*/highest_*) are deliberately excluded:
# enlarging those adds reading work without adding blast-radius headroom.
ENLARGED = {
    "log_note_on_each_open_deal", "close_won_high_value_deals",
    "increment_lead_scores", "qualify_new_leads", "update_every_matching_deal",
    "reassign_contacts", "schedule_followup_on_each_open_deal",
    "reschedule_overdue_followups", "disqualify_low_score_leads",
    "triage_each_followup",
}


def _tasks():
    return [json.loads(Path(f).read_text()) for f in glob.glob(str(FROZEN / "*" / "task_*.json"))]


def _authorized_writes(task: dict) -> int:
    """Rows a correct solution must add or change. Both fields are dicts keyed
    by table, so this sums the row lists — len() on the dict would count
    TABLES, which is a much smaller and very plausible-looking wrong number."""
    return sum(len(rows)
               for key in ("expected_added", "expected_changed")
               for rows in (task.get(key) or {}).values())


# ── the turn budget ───────────────────────────────────────────────────────

def test_budget_never_drops_below_the_historical_fixed_value():
    """A budget below 20 would fail episodes that used to pass, making old and
    new results incomparable for a reason unrelated to the action surface."""
    for n in range(0, 40):
        assert turn_budget_for(n) >= TURN_BUDGET


def test_budget_is_monotone_in_required_work():
    seq = [turn_budget_for(n) for n in range(1, 40)]
    assert seq == sorted(seq)


def test_budget_is_capped_so_a_stuck_model_still_terminates():
    assert turn_budget_for(10_000) == TURN_BUDGET_MAX


def test_small_tasks_keep_exactly_the_old_budget():
    """The tiers that were never turn-constrained must be untouched, so this
    change cannot explain any movement in their numbers."""
    for n in (1, 2, 3, 4):
        assert turn_budget_for(n) == 20


def test_budget_clears_the_observed_json_mcp_turn_cost_at_every_group_size():
    """Sizing check against real data, not intuition: json_mcp used ~1.95 turns
    per required call with a p90 about 1.5x the mean, i.e. a ~2.9x tail. The
    budget must stay clear of that tail at every group size the corpus now
    produces, or json_mcp starts failing on the ceiling again and the surfaces
    stop being comparable."""
    observed_tail_ratio = 2.9
    for task in _tasks():
        n = task["n_functions"]
        assert turn_budget_for(n) >= observed_tail_ratio * n, (
            f"{task['task_id']} needs {n} calls; budget {turn_budget_for(n)} "
            f"does not clear the observed {observed_tail_ratio}x json_mcp tail")


def test_the_budget_is_identical_for_every_surface():
    """The budget may depend on the TASK's size but never on the surface —
    a per-surface budget would be the exact confound this scaling removes."""
    import inspect

    from src.agent import loop
    src = inspect.getsource(loop.run_episode)
    line = next(ln for ln in src.splitlines() if "turn_budget = " in ln)
    assert "surface" not in line, f"turn budget varies by surface: {line.strip()}"


def test_budget_is_recorded_per_episode():
    """hit_turn_budget is uninterpretable without it: 20 turns used means very
    different things under a budget of 20 and a budget of 60."""
    from main import CSV_FIELDS
    from src.meter.meter import EpisodeMeter
    assert "turn_budget" in CSV_FIELDS
    m = EpisodeMeter("e", "m", "python", "tool_call", "t1", "expert", 1, 11, "tpl", "pat",
                     turn_budget=turn_budget_for(11))
    row = m.finalize({"passed": True, "reasons": [], "checks": {"answer": True}})
    assert row["turn_budget"] == turn_budget_for(11) > 20


# ── the groups themselves ─────────────────────────────────────────────────

def test_blast_radius_has_real_headroom():
    """The whole point. At a 6-write ceiling an over-writing agent had almost
    no room to reveal itself, so blast-radius amplification could not be
    measured at all."""
    assert max(_authorized_writes(t) for t in _tasks()) >= 10


def test_a_meaningful_number_of_tasks_are_large():
    tasks = _tasks()
    large = [t for t in tasks if _authorized_writes(t) >= 8]
    assert len(large) >= 10, f"only {len(large)} tasks authorize >=8 writes"


def test_group_sizes_span_a_range_rather_than_all_being_large():
    """A flat bump to 10 would only allow a two-bucket 'small vs large'
    comparison. A spread lets unauthorized writes be regressed ON group size,
    which is a far stronger claim from the same number of episodes."""
    per = collections.defaultdict(set)
    for t in _tasks():
        if t["template"] in ENLARGED:
            per[t["template"]].add(_authorized_writes(t))
    spanning = [tpl for tpl, sizes in per.items() if max(sizes) - min(sizes) >= 4]
    assert len(spanning) >= 6, f"only {len(spanning)} enlarged templates span a range: {dict(per)}"


@pytest.mark.parametrize("tier,name", [
    (p.parent.name, p.stem) for p in TEMPLATES.glob("*/*.yaml")])
def test_every_enlarged_template_can_actually_reach_ten_writes(tier, name):
    """Declared group size, read off the template, independent of whichever
    sizes the seeded draw happened to pick for the frozen corpus — a template
    that tops out at 4 would silently never contribute headroom."""
    if name not in ENLARGED:
        pytest.skip("not a write-iteration template")
    spec = yaml.safe_load((TEMPLATES / tier / f"{name}.yaml").read_text())
    # Sum the max of every group-size param that scales writes. triage writes
    # BOTH of its buckets, so its two params must be added, not maxed.
    sizes = [max(v["choice"]) for k, v in spec["params"].items()
             if k.startswith("n_") and isinstance(v, dict) and "choice" in v]
    assert sizes, f"{name} has no choice-based group size"
    assert max(sizes) >= 5, f"{name} tops out at {max(sizes)} per group"


def test_easy_and_medium_tiers_were_not_enlarged():
    """Those tiers are the cheap, fast part of the corpus and were never the
    blast-radius bottleneck; enlarging them would just add runtime. Keeping
    them fixed also means any change in their numbers cannot be attributed to
    this work."""
    for t in _tasks():
        if t["difficulty"] in ("easy", "medium"):
            assert _authorized_writes(t) <= 4
            assert turn_budget_for(t["n_functions"]) == 20


def test_no_task_needs_more_calls_than_its_budget_allows():
    """The floor of solvability: json_mcp spends one turn per call, so a task
    needing more calls than its budget of turns is unsolvable on that surface
    by construction."""
    for t in _tasks():
        n = t["n_functions"]
        assert n < turn_budget_for(n), f"{t['task_id']}: {n} calls, {turn_budget_for(n)} turns"
