# test_task_sampling.py — the --limit subset must be the SAME tasks for every
# model, surface and trial. If two surfaces were ever compared on different
# task sets the whole study would be meaningless, so the invariance is pinned
# here rather than trusted to the seeding staying correct.
from __future__ import annotations

from collections import Counter

from main import _sample_tasks

TASKS = [{"task_id": f"task_{i:03d}", "difficulty": tier}
         for tier in ("easy", "medium", "hard", "expert")
         for i in range(60)]


def _ids(tasks):
    return [t["task_id"] for t in tasks]


def test_sample_is_identical_across_calls():
    """The property the comparison rests on: same seed -> same tasks, always."""
    first = _ids(_sample_tasks(TASKS, 20, 0))
    for _ in range(10):
        assert _ids(_sample_tasks(TASKS, 20, 0)) == first


def test_sample_does_not_depend_on_input_order():
    """load_tasks() order must not leak into the draw — otherwise a corpus
    rebuild that reorders files would silently change the subset."""
    shuffled = list(reversed(TASKS))
    assert set(_ids(_sample_tasks(TASKS, 20, 0))) == set(_ids(_sample_tasks(shuffled, 20, 0)))


def test_different_seed_gives_different_but_reproducible_subset():
    a = _ids(_sample_tasks(TASKS, 20, 0))
    b = _ids(_sample_tasks(TASKS, 20, 7))
    assert a != b
    assert b == _ids(_sample_tasks(TASKS, 20, 7))


def test_limit_applies_per_tier_not_globally():
    sample = _sample_tasks(TASKS, 15, 0)
    assert Counter(t["difficulty"] for t in sample) == {
        "easy": 15, "medium": 15, "hard": 15, "expert": 15}


def test_limit_at_or_above_tier_size_returns_everything():
    assert len(_sample_tasks(TASKS, 60, 0)) == len(TASKS)
    assert len(_sample_tasks(TASKS, 999, 0)) == len(TASKS)


def test_sample_is_ordered_by_task_id():
    """Runs should read in a stable order rather than shuffled."""
    for tier_tasks in (_sample_tasks(TASKS, 20, 0),):
        by_tier: dict[str, list[str]] = {}
        for t in tier_tasks:
            by_tier.setdefault(t["difficulty"], []).append(t["task_id"])
        for ids in by_tier.values():
            assert ids == sorted(ids)


def test_one_tier_size_change_does_not_shift_another_tiers_draw():
    """Seeding per tier means regenerating one tier cannot silently change
    which tasks another tier contributes."""
    baseline = [t for t in _sample_tasks(TASKS, 20, 0) if t["difficulty"] == "easy"]
    grown = TASKS + [{"task_id": f"task_{i:03d}", "difficulty": "expert"} for i in range(60, 90)]
    after = [t for t in _sample_tasks(grown, 20, 0) if t["difficulty"] == "easy"]
    assert _ids(baseline) == _ids(after)
