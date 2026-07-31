# audit.py — named, re-runnable invariant checks over every frozen
# task+world pair. These replace the old generator's inline rejection
# guards: instead of trusting that construction-time logic was right, every
# invariant is re-asked EMPIRICALLY against the finished artifacts. A
# failure names the task and the broken invariant at freeze time — a
# template bug can never silently ship ambiguous or unsolvable tasks.
#
# Run: python3 -m src.db.scenarios.crm_scenario.tasks.audit
from __future__ import annotations

import shutil
import sqlite3
import tempfile
from pathlib import Path

from src.db import db
from src.db.scenarios.crm_scenario.crm_db import SIM_TODAY, TABLES
from src.db.scenarios.crm_scenario.tasks import template_interpreter as ti
from src.db.scenarios.crm_scenario.tasks import world_builder as wb
from src.db.scenarios.crm_scenario.tasks.build_tasks import load_tasks
from src.verifier.verify import verify

# NOT NULL columns the partial expected_added specs don't carry — the golden
# solution fills them with neutral values (superset-match ignores extras).
_ADD_FILLERS = {
    "activities": {"ts": f"{SIM_TODAY}T12:00:00", "rep_id": 1},
    "followups": {"status": "open", "rep_id": 1},
}


def _conn(path) -> sqlite3.Connection:
    return db.connect(path)


# ── generic invariants (every task) ──────────────────────────────────────

def check_golden_solution(task: dict, world: Path, tmp: Path) -> str | None:
    """Apply the expected mutations directly via SQL; the diff + ground_truth
    must pass verify(). Proves task/world/verifier coherence."""
    work = tmp / f"golden_{task['task_id']}.sqlite"
    shutil.copyfile(world, work)
    baseline = db.snapshot(work)
    conn = _conn(work)
    try:
        for table, specs in task["expected_changed"].items():
            for spec in specs:
                sets = ", ".join(f"{c}=?" for c in spec["fields"])
                conn.execute(f"UPDATE {table} SET {sets} WHERE id=?",
                             (*spec["fields"].values(), spec["id"]))
        for table, rows in task["expected_added"].items():
            for row in rows:
                full = {**_ADD_FILLERS.get(table, {}), **row}
                cols = ", ".join(full)
                ph = ", ".join("?" for _ in full)
                conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({ph})",
                             list(full.values()))
        conn.commit()
    finally:
        conn.close()
    diff = db.state_diff(baseline, work, TABLES)
    result = verify(task, diff, task["ground_truth"])
    if not result["passed"]:
        return f"golden solution failed verify(): {result['reasons']}"
    return None


def check_no_op_changes(task: dict, world: Path, tmp: Path) -> str | None:
    conn = _conn(world)
    try:
        for table, specs in task["expected_changed"].items():
            for spec in specs:
                current = conn.execute(f"SELECT * FROM {table} WHERE id=?",
                                        (spec["id"],)).fetchone()
                if current is None:
                    return f"expected_changed row {table}.id={spec['id']} does not exist"
                for col, target in spec["fields"].items():
                    if current[col] == target:
                        return f"no-op change: {table}.{col} already = {target!r}"
    finally:
        conn.close()
    return None


# ── per-template anchor/closed-set invariants ────────────────────────────

def _count(conn, sql, *args) -> int:
    return conn.execute(sql, args).fetchone()[0]


def check_anchor_unique(task: dict, world: Path, tmp: Path) -> str | None:
    conn = _conn(world)
    try:
        t = task["template"]
        gt = task["ground_truth"]
        if t in ("act_on_a_deal", "decide_by_deal_value"):
            row = conn.execute(
                "SELECT d.stage, c.company FROM deals d JOIN leads l ON d.lead_id=l.id "
                "JOIN contacts c ON l.contact_id=c.id WHERE d.id=?", (gt["deal_id"],)).fetchone()
            n = _count(conn, "SELECT COUNT(*) FROM deals d JOIN leads l ON d.lead_id=l.id "
                              "JOIN contacts c ON l.contact_id=c.id WHERE d.stage=? AND c.company=?",
                       row["stage"], row["company"])
            if n != 1:
                return f"'{row['stage']} deal with {row['company']}' matches {n} deals, not 1"
        elif t == "act_on_a_followup":
            row = conn.execute(
                "SELECT c.company FROM followups f JOIN deals d ON f.deal_id=d.id "
                "JOIN leads l ON d.lead_id=l.id JOIN contacts c ON l.contact_id=c.id "
                "WHERE f.id=?", (gt["followup_id"],)).fetchone()
            n = _count(conn, "SELECT COUNT(*) FROM followups f JOIN deals d ON f.deal_id=d.id "
                              "JOIN leads l ON d.lead_id=l.id JOIN contacts c ON l.contact_id=c.id "
                              "WHERE c.company=? AND f.status='open' AND f.due_date<?",
                       row["company"], SIM_TODAY)
            if n != 1:
                return f"'overdue follow-up on the {row['company']} deal' matches {n}, not 1"
        elif t == "act_on_a_lead":
            row = conn.execute(
                "SELECT c.name FROM leads l JOIN contacts c ON l.contact_id=c.id "
                "WHERE l.id=?", (gt["lead_id"],)).fetchone()
            n = _count(conn, "SELECT COUNT(*) FROM leads l JOIN contacts c ON l.contact_id=c.id "
                              "WHERE c.name=? AND l.status='new'", row["name"])
            if n != 1:
                return f"'new lead from {row['name']}' matches {n} leads, not 1"
        elif t == "act_on_a_contact":
            row = conn.execute("SELECT name, company FROM contacts WHERE id=?",
                                (gt["contact_id"],)).fetchone()
            n = _count(conn, "SELECT COUNT(*) FROM contacts WHERE name=? AND company=?",
                       row["name"], row["company"])
            if n != 1:
                return f"'contact {row['name']} at {row['company']}' matches {n}, not 1"
        elif t == "find_deal_via_chain":
            deal = conn.execute(
                "SELECT d.lead_id, l.contact_id, c.name, c.company FROM deals d "
                "JOIN leads l ON d.lead_id=l.id JOIN contacts c ON l.contact_id=c.id "
                "WHERE d.id=?", (gt["deal_id"],)).fetchone()
            n = _count(conn, "SELECT COUNT(*) FROM contacts WHERE name=? AND company=?",
                       deal["name"], deal["company"])
            if n != 1:
                return f"chained contact matches {n}, not 1"
            newest = conn.execute(
                "SELECT id, created_at FROM leads WHERE contact_id=? "
                "ORDER BY created_at DESC LIMIT 2", (deal["contact_id"],)).fetchall()
            if len(newest) > 1 and newest[0]["created_at"] == newest[1]["created_at"]:
                return "chained 'most recent lead' is a tie"
            if newest[0]["id"] != deal["lead_id"]:
                return "chained anchor is not under the most recent lead"
            n = _count(conn, "SELECT COUNT(*) FROM deals WHERE lead_id=? AND stage='negotiation'",
                       deal["lead_id"])
            if n != 1:
                return f"chained lead has {n} negotiation deals, not 1"
    finally:
        conn.close()
    return None


def check_closed_sets(task: dict, world: Path, tmp: Path) -> str | None:
    conn = _conn(world)
    try:
        t = task["template"]
        gt = task["ground_truth"]
        if t == "update_every_matching_deal":
            rep = task["query"].split("owned by ")[1].split(" to the")[0]
            n = _count(conn, "SELECT COUNT(*) FROM deals d JOIN reps r ON d.rep_id=r.id "
                              "WHERE r.name=? AND d.stage='prospecting'", rep)
            if n != gt["n_updated"]:
                return f"bulk group has {n} matching deals, ground truth says {gt['n_updated']}"
        elif t == "triage_each_followup":
            rep = task["query"].split("follow-up on ")[1].split("'s deals")[0]
            if _count(conn, "SELECT COUNT(*) FROM reps WHERE name=?", rep) != 1:
                return f"iterative rep name {rep!r} is not unique"
            rows = conn.execute(
                "SELECT f.due_date FROM followups f JOIN deals d ON f.deal_id=d.id "
                "JOIN reps r ON d.rep_id=r.id WHERE r.name=? AND f.status='open'", (rep,)).fetchall()
            from datetime import date
            today = date.fromisoformat(SIM_TODAY)
            high = sum(1 for r in rows
                       if (today - date.fromisoformat(r["due_date"])).days > 7)
            low = len(rows) - high
            if high != gt["n_escalated"]:
                return f"{high} follow-ups overdue >7d, ground truth says {gt['n_escalated']}"
            if high == 0 or low == 0:
                return f"iterative branches not both represented (high={high}, low={low})"
        elif t == "count_open_deals":
            rep = task["query"].split("does ")[1].split(" currently")[0]
            if _count(conn, "SELECT COUNT(*) FROM reps WHERE name=?", rep) != 1:
                return f"lookup rep name {rep!r} is not unique"
            n = _count(conn, "SELECT COUNT(*) FROM deals d JOIN reps r ON d.rep_id=r.id "
                              "WHERE r.name=? AND d.stage NOT IN ('won','lost')", rep)
            if n != gt["n_deals"]:
                return f"rep owns {n} open deals, ground truth says {gt['n_deals']}"
        elif t == "log_note_on_each_open_deal":
            rep = task["query"].replace("\n", " ").split("owned by ")[1].split(".")[0].strip()
            if _count(conn, "SELECT COUNT(*) FROM reps WHERE name=?", rep) != 1:
                return f"iterative rep name {rep!r} is not unique"
            n = _count(conn, "SELECT COUNT(*) FROM deals d JOIN reps r ON d.rep_id=r.id "
                              "WHERE r.name=? AND d.stage NOT IN ('won','lost')", rep)
            if n != gt["n_logged"]:
                return f"rep owns {n} open deals, ground truth says {gt['n_logged']}"
        elif t == "sum_deals_in_stages":
            rep = task["query"].replace("\n", " ").split("Sum the value of ")[1].split("'s deals")[0]
            if _count(conn, "SELECT COUNT(*) FROM reps WHERE name=?", rep) != 1:
                return f"lookup rep name {rep!r} is not unique"
            total = conn.execute(
                "SELECT COALESCE(SUM(d.value),0) FROM deals d JOIN reps r ON d.rep_id=r.id "
                "WHERE r.name=? AND d.stage IN ('proposal','negotiation')", (rep,)).fetchone()[0]
            if total != gt["total_value"]:
                return f"in-stage deals sum to {total}, ground truth says {gt['total_value']}"
        elif t == "followups_due_within_window":
            q = task["query"].replace("\n", " ")
            rep = q.split("How many of ")[1].split("'s follow")[0]
            cutoff = q.split("on or before ")[1].split("?")[0]
            if _count(conn, "SELECT COUNT(*) FROM reps WHERE name=?", rep) != 1:
                return f"lookup rep name {rep!r} is not unique"
            n = _count(conn, "SELECT COUNT(*) FROM followups f JOIN deals d ON f.deal_id=d.id "
                              "JOIN reps r ON d.rep_id=r.id WHERE r.name=? AND f.due_date<=?",
                       rep, cutoff)
            if n != gt["n_due"]:
                return f"rep has {n} follow-ups due on/before {cutoff}, ground truth says {gt['n_due']}"
            # boundary safety: no follow-up within a day of the cutoff
            from datetime import date
            cd = date.fromisoformat(cutoff)
            dues = conn.execute(
                "SELECT f.due_date FROM followups f JOIN deals d ON f.deal_id=d.id "
                "JOIN reps r ON d.rep_id=r.id WHERE r.name=?", (rep,)).fetchall()
            if any(abs((date.fromisoformat(x["due_date"]) - cd).days) < 2 for x in dues):
                return f"a follow-up is within 1 day of the cutoff {cutoff} (ambiguous)"
        elif t == "open_deals_without_followups":
            rep = task["query"].replace("\n", " ").split("How many of ")[1].split("'s open")[0]
            if _count(conn, "SELECT COUNT(*) FROM reps WHERE name=?", rep) != 1:
                return f"lookup rep name {rep!r} is not unique"
            n = _count(conn, "SELECT COUNT(*) FROM deals d JOIN reps r ON d.rep_id=r.id "
                              "WHERE r.name=? AND d.stage NOT IN ('won','lost') AND NOT EXISTS "
                              "(SELECT 1 FROM followups f WHERE f.deal_id=d.id)", rep)
            if n != gt["n_bare"]:
                return f"rep has {n} open deals without follow-ups, ground truth says {gt['n_bare']}"
        elif t == "schedule_followup_on_each_open_deal":
            rep = task["query"].replace("\n", " ").split("owned by ")[1].split(".")[0].strip()
            if _count(conn, "SELECT COUNT(*) FROM reps WHERE name=?", rep) != 1:
                return f"iterative rep name {rep!r} is not unique"
            n = _count(conn, "SELECT COUNT(*) FROM deals d JOIN reps r ON d.rep_id=r.id "
                              "WHERE r.name=? AND d.stage NOT IN ('won','lost')", rep)
            if n != gt["n_scheduled"]:
                return f"rep owns {n} open deals, ground truth says {gt['n_scheduled']}"
        elif t == "second_highest_value_deal":
            contact = task["query"].replace("\n", " ").split("Among ")[1].split("'s deals")[0]
            if _count(conn, "SELECT COUNT(*) FROM contacts WHERE name=?", contact) != 1:
                return f"lookup contact name {contact!r} is not unique"
            rows = conn.execute(
                "SELECT d.id, d.value FROM deals d JOIN leads l ON d.lead_id=l.id "
                "JOIN contacts c ON l.contact_id=c.id WHERE c.name=? ORDER BY d.value DESC",
                (contact,)).fetchall()
            if len(rows) < 3:
                return f"only {len(rows)} deals for the contact, need >= 3 to rank a runner-up"
            if rows[1]["id"] != gt["deal_id"]:
                return f"second-highest deal is id={rows[1]['id']}, ground truth says {gt['deal_id']}"
            # clear gaps both sides of the runner-up: below the winner, above the rest
            if rows[0]["value"] < 1.25 * rows[1]["value"]:
                return f"near-tie at top: winner {rows[0]['value']} within 25% of runner-up {rows[1]['value']}"
            if rows[1]["value"] < 1.25 * rows[2]["value"]:
                return f"near-tie below: runner-up {rows[1]['value']} within 25% of third {rows[2]['value']}"
        elif t == "total_pipeline_for_company":
            company = task["query"].replace("\n", " ").split("open deals at ")[1].split("?")[0]
            n_contacts = _count(conn, "SELECT COUNT(*) FROM contacts WHERE company=?", company)
            if n_contacts < 2:
                return f"company {company!r} has {n_contacts} contacts, expected the planted 2+"
            total = conn.execute(
                "SELECT COALESCE(SUM(d.value),0) FROM deals d JOIN leads l ON d.lead_id=l.id "
                "JOIN contacts c ON l.contact_id=c.id WHERE c.company=? "
                "AND d.stage NOT IN ('won','lost')", (company,)).fetchone()[0]
            if total != gt["total_value"]:
                return f"company open pipeline sums to {total}, ground truth says {gt['total_value']}"
        elif t == "most_common_lead_source":
            contact = task["query"].replace("\n", " ").split("among ")[1].split("'s leads")[0]
            if _count(conn, "SELECT COUNT(*) FROM contacts WHERE name=?", contact) != 1:
                return f"lookup contact name {contact!r} is not unique"
            rows = conn.execute(
                "SELECT l.source, COUNT(*) n FROM leads l JOIN contacts c ON l.contact_id=c.id "
                "WHERE c.name=? GROUP BY l.source ORDER BY n DESC", (contact,)).fetchall()
            if rows[0]["source"] != gt["source"]:
                return f"mode source is {rows[0]['source']!r}, ground truth says {gt['source']!r}"
            if len(rows) > 1 and rows[0]["n"] == rows[1]["n"]:
                return f"mode is a tie: {rows[0]['source']} and {rows[1]['source']} both {rows[0]['n']}"
        elif t == "disqualify_low_score_leads":
            contact = task["query"].replace("\n", " ").split("belonging to ")[1].split(" with")[0]
            if _count(conn, "SELECT COUNT(*) FROM contacts WHERE name=?", contact) != 1:
                return f"iterative contact name {contact!r} is not unique"
            rows = conn.execute(
                "SELECT l.score FROM leads l JOIN contacts c ON l.contact_id=c.id WHERE c.name=?",
                (contact,)).fetchall()
            low = sum(1 for x in rows if x["score"] < 30)
            high = len(rows) - low
            if low != gt["n_updated"]:
                return f"{low} leads below 30, ground truth says {gt['n_updated']}"
            if low == 0 or high == 0:
                return f"conditional branches not both represented (low={low}, high={high})"
            for x in rows:
                if abs(x["score"] - 30) < 5:
                    return f"near-tie: lead score={x['score']} within 5 of cutoff 30"
        elif t == "count_contacts_without_leads":
            rep = task["query"].replace("\n", " ").split("How many of ")[1].split("'s contacts")[0]
            if _count(conn, "SELECT COUNT(*) FROM reps WHERE name=?", rep) != 1:
                return f"lookup rep name {rep!r} is not unique"
            n = _count(conn, "SELECT COUNT(*) FROM contacts c JOIN reps r ON c.rep_id=r.id "
                              "WHERE r.name=? AND NOT EXISTS "
                              "(SELECT 1 FROM leads l WHERE l.contact_id=c.id)", rep)
            if n != gt["n_orphan"]:
                return f"rep has {n} lead-less contacts, ground truth says {gt['n_orphan']}"
        elif t == "followup_on_top_deal":
            contact = task["query"].replace("\n", " ").split(" on ")[1].split("'s highest")[0]
            if _count(conn, "SELECT COUNT(*) FROM contacts WHERE name=?", contact) != 1:
                return f"lookup contact name {contact!r} is not unique"
            rows = conn.execute(
                "SELECT d.id, d.value FROM deals d JOIN leads l ON d.lead_id=l.id "
                "JOIN contacts c ON l.contact_id=c.id WHERE c.name=? ORDER BY d.value DESC",
                (contact,)).fetchall()
            if rows[0]["id"] != gt["deal_id"]:
                return f"highest-value deal is id={rows[0]['id']}, ground truth says {gt['deal_id']}"
            if len(rows) > 1 and rows[0]["value"] < 1.3 * rows[1]["value"]:
                return (f"near-tie: winner value={rows[0]['value']} within 30% of "
                        f"runner-up {rows[1]['value']}")
        elif t == "increment_lead_scores":
            contact = task["query"].replace("\n", " ").split("belonging to ")[1].split(".")[0].strip()
            if _count(conn, "SELECT COUNT(*) FROM contacts WHERE name=?", contact) != 1:
                return f"iterative contact name {contact!r} is not unique"
            n = _count(conn, "SELECT COUNT(*) FROM leads l JOIN contacts c ON l.contact_id=c.id "
                              "WHERE c.name=?", contact)
            if n != gt["n_updated"]:
                return f"contact has {n} leads, ground truth says {gt['n_updated']}"
            # +10 must stay within the 0..100 score range for every lead
            over = _count(conn, "SELECT COUNT(*) FROM leads l JOIN contacts c ON l.contact_id=c.id "
                                 "WHERE c.name=? AND l.score > 90", contact)
            if over:
                return f"{over} lead(s) have score > 90; +10 would exceed the 0..100 range"
        elif t == "count_overdue_followups":
            rep = task["query"].replace("\n", " ").split("How many of ")[1].split("'s follow")[0]
            if _count(conn, "SELECT COUNT(*) FROM reps WHERE name=?", rep) != 1:
                return f"lookup rep name {rep!r} is not unique"
            n = _count(conn, "SELECT COUNT(*) FROM followups f JOIN deals d ON f.deal_id=d.id "
                              "JOIN reps r ON d.rep_id=r.id WHERE r.name=? AND f.status='open' "
                              "AND f.due_date < ?", rep, SIM_TODAY)
            if n != gt["n_overdue"]:
                return f"rep has {n} overdue follow-ups, ground truth says {gt['n_overdue']}"
        elif t == "reschedule_overdue_followups":
            rep = task["query"].replace("\n", " ").split("follow-up on ")[1].split("'s deals")[0]
            if _count(conn, "SELECT COUNT(*) FROM reps WHERE name=?", rep) != 1:
                return f"iterative rep name {rep!r} is not unique"
            n = _count(conn, "SELECT COUNT(*) FROM followups f JOIN deals d ON f.deal_id=d.id "
                              "JOIN reps r ON d.rep_id=r.id WHERE r.name=? AND f.status='open' "
                              "AND f.due_date < ?", rep, SIM_TODAY)
            if n != gt["n_rescheduled"]:
                return f"rep has {n} overdue follow-ups, ground truth says {gt['n_rescheduled']}"
        elif t == "close_won_high_value_deals":
            q = task["query"].replace("\n", " ")
            rep = q.split("owned by ")[1].split(" that")[0]
            threshold = float(q.split("$")[1].split(" ")[0].rstrip(",.").replace(",", ""))
            if _count(conn, "SELECT COUNT(*) FROM reps WHERE name=?", rep) != 1:
                return f"iterative rep name {rep!r} is not unique"
            rows = conn.execute(
                "SELECT d.value FROM deals d JOIN reps r ON d.rep_id=r.id "
                "WHERE r.name=? AND d.stage='closing'", (rep,)).fetchall()
            over = sum(1 for x in rows if x["value"] > threshold)
            under = len(rows) - over
            if over != gt["n_won"]:
                return f"{over} closing deals over ${threshold}, ground truth says {gt['n_won']}"
            if over == 0 or under == 0:
                return f"conditional branches not both represented (over={over}, under={under})"
            for x in rows:
                if abs(x["value"] - threshold) < 0.2 * threshold:
                    return f"near-tie: deal value={x['value']} within 20% of threshold {threshold}"
        elif t == "count_calls_for_rep":
            rep = task["query"].replace("\n", " ").split("logged on ")[1].split("'s deals")[0]
            if _count(conn, "SELECT COUNT(*) FROM reps WHERE name=?", rep) != 1:
                return f"lookup rep name {rep!r} is not unique"
            n = _count(conn, "SELECT COUNT(*) FROM activities a JOIN deals d ON a.deal_id=d.id "
                              "JOIN reps r ON d.rep_id=r.id WHERE r.name=? AND a.type='call'", rep)
            if n != gt["n_calls"]:
                return f"rep has {n} call activities, ground truth says {gt['n_calls']}"
        elif t == "qualify_new_leads":
            contact = task["query"].replace("\n", " ").split("belonging to ")[1].split(" as qualified")[0]
            if _count(conn, "SELECT COUNT(*) FROM contacts WHERE name=?", contact) != 1:
                return f"lookup contact name {contact!r} is not unique"
            n = _count(conn, "SELECT COUNT(*) FROM leads l JOIN contacts c ON l.contact_id=c.id "
                              "WHERE c.name=? AND l.status='new'", contact)
            if n != gt["n_qualified"]:
                return f"contact has {n} new leads, ground truth says {gt['n_qualified']}"
        elif t == "highest_value_deal_for_contact":
            contact = task["query"].replace("\n", " ").split("Among ")[1].split("'s deals")[0]
            if _count(conn, "SELECT COUNT(*) FROM contacts WHERE name=?", contact) != 1:
                return f"lookup contact name {contact!r} is not unique"
            rows = conn.execute(
                "SELECT d.id, d.value FROM deals d JOIN leads l ON d.lead_id=l.id "
                "JOIN contacts c ON l.contact_id=c.id WHERE c.name=? ORDER BY d.value DESC",
                (contact,)).fetchall()
            if rows[0]["id"] != gt["deal_id"]:
                return f"highest-value deal is id={rows[0]['id']}, ground truth says {gt['deal_id']}"
            if len(rows) > 1 and rows[0]["value"] < 1.3 * rows[1]["value"]:
                return (f"near-tie: winner value={rows[0]['value']} within 30% of "
                        f"runner-up {rows[1]['value']}")
        elif t == "reassign_contacts":
            # "...owned by {from} to {to}. Report..." — both rep names must be
            # unique (so "owned by X" and "to Y" each resolve to one rep), and
            # the source's contact count is the group that must move.
            from_rep = task["query"].split("owned by ")[1].split(" to ")[0]
            to_rep = task["query"].split(" to ")[1].split(".")[0]
            for name, role in ((from_rep, "source"), (to_rep, "target")):
                if _count(conn, "SELECT COUNT(*) FROM reps WHERE name=?", name) != 1:
                    return f"{role} rep name {name!r} is not unique"
            n = _count(conn, "SELECT COUNT(*) FROM contacts c JOIN reps r ON c.rep_id=r.id "
                              "WHERE r.name=?", from_rep)
            if n != gt["n_moved"]:
                return f"source rep owns {n} contacts, ground truth says {gt['n_moved']}"
    finally:
        conn.close()
    return None


# Which (table, column) writes the tool API actually offers, derived from the
# tool arg models so it can never drift from the real tools. The tool->table
# mapping is domain knowledge (a tool name does not name its table), kept here
# as the one explicit fact; the writable COLUMNS come straight from each model.
def _writable_fields() -> dict[str, set[str]]:
    from src.tool_server import models as M
    updaters = {"contacts": M.UpdateContactArgs, "leads": M.UpdateLeadArgs,
                "deals": M.UpdateDealArgs, "followups": M.UpdateFollowupArgs}
    return {table: set(model.model_fields) - {"id"} for table, model in updaters.items()}


# Tables a create/log/schedule tool can add rows to.
_CREATABLE_TABLES = {"contacts", "leads", "deals", "activities", "followups"}


def check_tool_solvable(task: dict, world: Path, tmp: Path) -> str | None:
    """Every write the task requires must be one the tool API can actually make.

    The golden-solution check applies expected state via direct SQL, so it
    confirms the goal is a valid DATABASE state — but not that an agent, which
    has only the tools, can reach it. A task that must change a column no tool
    exposes (e.g. a deal's rep_id, which update_deal does not offer) would pass
    golden verification yet be impossible to complete. This closes that gap."""
    writable = _writable_fields()
    for table, specs in task["expected_changed"].items():
        offered = writable.get(table, set())
        for spec in specs:
            for field in spec["fields"]:
                if field not in offered:
                    return (f"unsolvable: task must change {table}.{field}, but no "
                            f"tool can write it (writable {table} fields: {sorted(offered)})")
    for table in task["expected_added"]:
        if table not in _CREATABLE_TABLES:
            return f"unsolvable: task must add a row to {table}, but no tool creates one"
    return None


def check_conditional_margin(task: dict, world: Path, tmp: Path) -> str | None:
    if task["template"] != "decide_by_deal_value":
        return None
    threshold = float(task["query"].split("over $")[1].split(" ")[0].rstrip(",.").replace(",", ""))
    conn = _conn(world)
    try:
        value = conn.execute("SELECT value FROM deals WHERE id=?",
                              (task["ground_truth"]["deal_id"],)).fetchone()["value"]
    finally:
        conn.close()
    went_high = bool(task["expected_changed"])
    if (value > threshold) != went_high:
        return f"branch mismatch: value={value}, threshold={threshold}, expected high={went_high}"
    if abs(value - threshold) < 0.2 * threshold:
        return f"near-tie: value={value} within 20% of threshold={threshold}"
    return None


def check_fingerprints(tasks: list[dict]) -> list[str]:
    """Corpus-level: anchor ids must be spread across each table's id range,
    not clustered where naive injection would put them (the top)."""
    problems = []
    positions = []
    for task in tasks:
        key = task["answer_keys"][0]
        table = {"deal_id": "deals", "lead_id": "leads",
                 "contact_id": "contacts", "followup_id": "followups"}.get(key)
        if not table:
            continue
        conn = _conn(task["world_db"])
        try:
            max_id = conn.execute(f"SELECT MAX(id) FROM {table}").fetchone()[0]
        finally:
            conn.close()
        positions.append(task["ground_truth"][key] / max_id)
    if positions:
        if min(positions) > 0.3:
            problems.append(f"anchor ids never in the low range (min percentile {min(positions):.2f})")
        if max(positions) < 0.7:
            problems.append(f"anchor ids never in the high range (max percentile {max(positions):.2f})")
        top = sum(1 for p in positions if p > 0.95)
        if top > len(positions) * 0.15:
            problems.append(f"{top}/{len(positions)} anchors in the top 5% of the id range")
    return problems


def check_rebuild_drift(task: dict, world: Path, tmp: Path) -> str | None:
    """Re-derive the world from the seed via the current generator; the
    frozen artifact must match logically. Proves generator and corpus
    haven't drifted apart."""
    template = ti.load_template(task["template"], task["difficulty"])
    rebuilt_path = tmp / f"rebuild_{task['task_id']}.sqlite"
    rebuilt = wb.build_task(task["world_seed"], template, rebuilt_path)

    frozen_contract = {k: v for k, v in task.items()
                       if k not in ("task_id", "world_seed", "difficulty", "template", "pattern", "world_db")}
    if rebuilt != frozen_contract:
        return "rebuilt task contract differs from frozen JSON (generator drift)"

    def dump(p):
        conn = _conn(p)
        try:
            return {t: sorted(tuple(dict(r).items())
                              for r in conn.execute(f"SELECT * FROM {t}")) for t in TABLES}
        finally:
            conn.close()
    if dump(rebuilt_path) != dump(world):
        return "rebuilt world differs from frozen artifact (generator drift)"
    return None


PER_TASK_CHECKS = [check_golden_solution, check_tool_solvable, check_no_op_changes,
                    check_anchor_unique, check_closed_sets, check_conditional_margin,
                    check_rebuild_drift]


def run(selector: str = "all") -> list[str]:
    tasks = load_tasks(selector)
    failures = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for task in tasks:
            world = Path(task["world_db"])
            for check in PER_TASK_CHECKS:
                problem = check(task, world, tmp)
                if problem:
                    failures.append(f"{task['task_id']} [{check.__name__}] {problem}")
    failures += [f"corpus [check_fingerprints] {p}" for p in check_fingerprints(tasks)]
    return failures


def main() -> None:
    failures = run()
    if failures:
        print(f"AUDIT FAILED — {len(failures)} problem(s):")
        for f in failures:
            print(" ", f)
        raise SystemExit(1)
    print("audit green: all invariants hold over the frozen corpus")


if __name__ == "__main__":
    main()
