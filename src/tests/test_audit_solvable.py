# test_audit_solvable.py — the tool-solvability audit exists because a template
# once required changing deals.rep_id, which no tool can do; the golden-solution
# check (direct SQL) passed it anyway. These pin the guard against that class.
from __future__ import annotations

from src.db.scenarios.crm_scenario.tasks.audit import check_tool_solvable


def test_change_to_unwritable_field_is_flagged():
    # update_deal offers stage/value/close_date — NOT rep_id
    task = {"expected_changed": {"deals": [{"id": 1, "fields": {"rep_id": 3}}]},
            "expected_added": {}}
    msg = check_tool_solvable(task, None, None)
    assert msg is not None and "deals.rep_id" in msg


def test_writable_field_passes():
    # update_contact DOES offer rep_id
    task = {"expected_changed": {"contacts": [{"id": 1, "fields": {"rep_id": 3}}]},
            "expected_added": {}}
    assert check_tool_solvable(task, None, None) is None


def test_add_to_uncreatable_table_is_flagged():
    task = {"expected_changed": {}, "expected_added": {"reps": [{"name": "x"}]}}
    msg = check_tool_solvable(task, None, None)
    assert msg is not None and "reps" in msg


def test_creatable_table_passes():
    task = {"expected_changed": {}, "expected_added": {"followups": [{"deal_id": 1}]}}
    assert check_tool_solvable(task, None, None) is None


def test_writable_fields_come_from_the_real_models():
    # a drift guard: the writable set must match the tool arg models exactly
    from src.db.scenarios.crm_scenario.tasks.audit import _writable_fields
    from src.tool_server import models as M
    w = _writable_fields()
    assert w["deals"] == set(M.UpdateDealArgs.model_fields) - {"id"}
    assert "rep_id" in w["contacts"]
    assert "rep_id" not in w["deals"]
