# tool_docs.py — the PROSE and RESULT-SHAPE half of a tool's definition.
#
# Argument names, types, required-ness and enum members come from the Pydantic
# models in models.py; the tool's description comes from its route docstring in
# server.py. What lives here is only what those cannot express: what each
# argument MEANS, a realistic example value, and what the tool hands back.
#
# WHY THIS IS KEYED BY TOOL, NOT BY MODEL
# ---------------------------------------
# Several tools share one args model — GetByIdArgs serves get_contact,
# get_lead and get_deal — but each needs its own wording ("the contact's id"
# vs "the lead's id"). Attaching prose to the model would force one generic
# description onto all three, so prose is keyed by tool name instead.
#
# WHY RETURN SHAPES ARE HERE AT ALL
# ---------------------------------
# They were once shown ONLY to the code-mode surfaces, so a code-mode model
# knew what fields a result had before calling anything while json_mcp had to
# spend a turn finding out — an information advantage masquerading as an
# action-surface advantage. Held in one place, every surface gets the same
# facts: as an example row (python/js/json_mcp) or as a typed interface (ts).
from __future__ import annotations

# tool name -> {argument -> what it means}. Enum members are NOT repeated here;
# they come from the type.
ARG_DOCS: dict[str, dict[str, str]] = {
    "find_contacts": {
        "name": "case-insensitive partial match on the contact's name",
        "email": "exact match on the contact's email",
        "company": "exact match on the contact's company",
        "rep_id": "only return contacts owned by this rep's id",
    },
    "get_contact": {
        "id": "the contact's id",
    },
    "find_leads": {
        "contact_id": "only return leads for this contact's id",
        "rep_id": "only return leads owned by this rep's id",
        "status": "only return leads with this status",
        "min_score": "only return leads with a score at or above this value",
    },
    "get_lead": {
        "id": "the lead's id",
    },
    "get_deal": {
        "id": "the deal's id",
    },
    "find_deals": {
        "lead_id": "only return deals under this lead's id",
        "stage": "only return deals in this pipeline stage",
        "rep_id": "only return deals owned by this rep's id",
        "min_value": "only return deals worth at least this amount",
    },
    "get_activities": {
        "deal_id": "only return activities on this deal's id",
        "contact_id": "only return activities on this contact's id",
    },
    "get_followups": {
        "deal_id": "only return follow-ups on this deal's id",
        "rep_id": "only return follow-ups owned by this rep's id",
        "status": "only return follow-ups with this status",
    },
    "create_contact": {
        "name": "the contact's full name",
        "email": "must be unique across all contacts",
        "rep_id": "the id of the rep who owns this contact",
    },
    "update_contact": {
        "id": "the contact's id",
        "email": "must be unique across all contacts",
        "rep_id": "reassign this contact to a different rep",
    },
    "create_lead": {
        "contact_id": "the contact this lead is for",
        "source": "how the lead came in",
        "score": "defaults to 50 if omitted",
        "rep_id": "defaults to the contact's own rep if omitted",
    },
    "update_lead": {
        "id": "the lead's id",
    },
    "create_deal": {
        "lead_id": "the lead this deal is under",
        "name": "a short label for the deal",
        "value": "the deal's monetary value",
        "stage": "defaults to \"prospecting\" if omitted",
        "close_date": "expected close date, \"YYYY-MM-DD\"",
    },
    "update_deal": {
        "id": "the deal's id",
        "close_date": "\"YYYY-MM-DD\"",
    },
    "log_activity": {
        "subject": "a short description of the activity",
        "deal_id": "the deal this activity is logged against",
        "contact_id": "the contact this activity is logged against",
    },
    "schedule_followup": {
        "deal_id": "the deal this follow-up is on",
        "due_date": "\"YYYY-MM-DD\"",
    },
    "update_followup": {
        "due_date": "\"YYYY-MM-DD\"",
    },
}

# tool name -> {argument -> a realistic value for the signature line}
ARG_EXAMPLES: dict[str, dict] = {
    "find_contacts": {'name': 'Alice', 'email': None, 'company': 'Wonka', 'rep_id': None},
    "get_contact": {'id': 7},
    "find_leads": {'contact_id': 7, 'rep_id': None, 'status': 'qualified', 'min_score': None},
    "get_lead": {'id': 12},
    "get_deal": {'id': 4},
    "find_deals": {'lead_id': None, 'stage': 'proposal', 'rep_id': None, 'min_value': 1000},
    "get_activities": {'deal_id': 4, 'contact_id': None},
    "get_followups": {'deal_id': 4, 'rep_id': None, 'status': 'open'},
    "create_contact": {'name': 'Bob Larsen', 'email': 'bob.larsen@wonka.example', 'rep_id': 6, 'company': 'Wonka', 'phone': '+1-555-8335'},
    "update_contact": {'id': 7, 'name': None, 'email': None, 'company': None, 'phone': '+1-555-9999', 'rep_id': None},
    "create_lead": {'contact_id': 7, 'source': 'referral', 'score': 72, 'rep_id': None},
    "update_lead": {'id': 12, 'status': 'qualified', 'score': None},
    "create_deal": {'lead_id': 12, 'name': 'Acme rollout', 'value': 45000, 'stage': 'prospecting', 'close_date': None},
    "update_deal": {'id': 4, 'stage': 'negotiation', 'value': None, 'close_date': None},
    "log_activity": {'type': 'call', 'subject': 'pricing', 'deal_id': 4, 'contact_id': None},
    "schedule_followup": {'deal_id': 4, 'due_date': '2026-06-04', 'note': 'confirm terms'},
    "update_followup": {'id': 9, 'status': 'done', 'due_date': '2026-06-11', 'note': 'confirm terms'},
}

# The row shapes tools return. Rendered as a typed interface for the TS
# surface, and as the example row above for the others.
RESULT_TYPES: dict[str, dict[str, str]] = {
    "Rep": {
        "id": "number",
        "name": "string",
        "email": "string",
        "team": "string",
        "active": "number",
    },
    "Contact": {
        "id": "number",
        "name": "string",
        "email": "string",
        "phone": "string | null",
        "company": "string | null",
        "rep_id": "number",
        "created_at": "string",
    },
    "Lead": {
        "id": "number",
        "contact_id": "number",
        "source": "\"webform\" | \"referral\" | \"event\" | \"cold_call\" | \"inbound_email\"",
        "score": "number",
        "status": "\"new\" | \"qualified\" | \"unqualified\" | \"converted\"",
        "rep_id": "number",
        "created_at": "string",
    },
    "Deal": {
        "id": "number",
        "lead_id": "number",
        "name": "string",
        "stage": "\"prospecting\" | \"qualification\" | \"proposal\" | \"negotiation\" | \"closing\" | \"won\" | \"lost\"",
        "value": "number",
        "currency": "string",
        "close_date": "string | null",
        "rep_id": "number",
        "created_at": "string",
    },
    "Activity": {
        "id": "number",
        "deal_id": "number | null",
        "contact_id": "number | null",
        "type": "\"call\" | \"email\" | \"meeting\" | \"note\"",
        "subject": "string",
        "ts": "string",
        "rep_id": "number",
    },
    "Followup": {
        "id": "number",
        "deal_id": "number",
        "due_date": "string",
        "note": "string | null",
        "status": "\"open\" | \"done\"",
        "rep_id": "number",
    },
}

# tool name -> how to describe what it returns, one example row, and the
# RESULT_TYPES entry it corresponds to (`many` = returns a list).
RETURN_DOCS: dict[str, dict] = {
    "list_reps": {
        "lead": "a list of reps, each shaped like:",
        "example": {'id': 3, 'name': 'Priya Chen', 'email': 'priya.chen@company.example', 'team': 'East', 'active': 1},
        "type": "Rep",
        "many": True,
    },
    "find_contacts": {
        "lead": "a list of contacts, each shaped like:",
        "example": {'id': 7, 'name': 'Alice Nakamura', 'email': 'alice.nakamura@wonka.example', 'phone': '+1-555-3362', 'company': 'Wonka', 'rep_id': 6, 'created_at': '2026-01-14'},
        "type": "Contact",
        "many": True,
    },
    "get_contact": {
        "lead": "one contact, shaped like:",
        "example": {'id': 7, 'name': 'Alice Nakamura', 'email': 'alice.nakamura@wonka.example', 'phone': '+1-555-3362', 'company': 'Wonka', 'rep_id': 6, 'created_at': '2026-01-14'},
        "type": "Contact",
        "many": False,
    },
    "find_leads": {
        "lead": "a list of leads, each shaped like:",
        "example": {'id': 12, 'contact_id': 7, 'source': 'referral', 'score': 72, 'status': 'qualified', 'rep_id': 6, 'created_at': '2026-01-20'},
        "type": "Lead",
        "many": True,
    },
    "get_lead": {
        "lead": "one lead, shaped like:",
        "example": {'id': 12, 'contact_id': 7, 'source': 'referral', 'score': 72, 'status': 'qualified', 'rep_id': 6, 'created_at': '2026-01-20'},
        "type": "Lead",
        "many": False,
    },
    "get_deal": {
        "lead": "one deal, shaped like:",
        "example": {'id': 4, 'lead_id': 12, 'name': 'Acme rollout', 'stage': 'proposal', 'value': 45000.0, 'currency': 'USD', 'close_date': '2026-06-01', 'rep_id': 3, 'created_at': '2026-01-15'},
        "type": "Deal",
        "many": False,
    },
    "find_deals": {
        "lead": "a list of deals, each shaped like:",
        "example": {'id': 4, 'lead_id': 12, 'name': 'Acme rollout', 'stage': 'proposal', 'value': 45000.0, 'currency': 'USD', 'close_date': '2026-06-01', 'rep_id': 3, 'created_at': '2026-01-15'},
        "type": "Deal",
        "many": True,
    },
    "get_activities": {
        "lead": "a list of activities, each shaped like:",
        "example": {'id': 21, 'deal_id': 4, 'contact_id': 12, 'type': 'call', 'subject': 'pricing', 'ts': '2026-02-01T12:00:00', 'rep_id': 3},
        "type": "Activity",
        "many": True,
    },
    "get_followups": {
        "lead": "a list of follow-ups, each shaped like:",
        "example": {'id': 9, 'deal_id': 4, 'due_date': '2026-06-04', 'note': 'confirm terms', 'status': 'open', 'rep_id': 3},
        "type": "Followup",
        "many": True,
    },
    "create_contact": {
        "lead": "the newly created contact, shaped like:",
        "example": {'id': 60, 'name': 'Bob Larsen', 'email': 'bob.larsen@wonka.example', 'phone': '+1-555-8335', 'company': 'Wonka', 'rep_id': 6, 'created_at': '2026-06-01'},
        "type": "Contact",
        "many": False,
    },
    "update_contact": {
        "lead": "the updated contact, shaped like:",
        "example": {'id': 7, 'name': 'Alice Nakamura', 'email': 'alice.nakamura@wonka.example', 'phone': '+1-555-9999', 'company': 'Wonka', 'rep_id': 6, 'created_at': '2026-01-14'},
        "type": "Contact",
        "many": False,
    },
    "create_lead": {
        "lead": "the newly created lead, shaped like:",
        "example": {'id': 12, 'contact_id': 7, 'source': 'referral', 'score': 72, 'status': 'new', 'rep_id': 6, 'created_at': '2026-06-01'},
        "type": "Lead",
        "many": False,
    },
    "update_lead": {
        "lead": "the updated lead, shaped like:",
        "example": {'id': 12, 'contact_id': 7, 'source': 'referral', 'score': 72, 'status': 'qualified', 'rep_id': 6, 'created_at': '2026-01-20'},
        "type": "Lead",
        "many": False,
    },
    "create_deal": {
        "lead": "the newly created deal, shaped like:",
        "example": {'id': 4, 'lead_id': 12, 'name': 'Acme rollout', 'stage': 'prospecting', 'value': 45000.0, 'currency': 'USD', 'close_date': None, 'rep_id': 6, 'created_at': '2026-06-01'},
        "type": "Deal",
        "many": False,
    },
    "update_deal": {
        "lead": "the updated deal, shaped like:",
        "example": {'id': 4, 'lead_id': 12, 'name': 'Acme rollout', 'stage': 'negotiation', 'value': 45000.0, 'currency': 'USD', 'close_date': '2026-06-01', 'rep_id': 3, 'created_at': '2026-01-15'},
        "type": "Deal",
        "many": False,
    },
    "log_activity": {
        "lead": "the newly created activity, shaped like:",
        "example": {'id': 21, 'deal_id': 4, 'contact_id': 12, 'type': 'call', 'subject': 'pricing', 'ts': '2026-06-01T12:00:00', 'rep_id': 3},
        "type": "Activity",
        "many": False,
    },
    "schedule_followup": {
        "lead": "the newly created follow-up, shaped like:",
        "example": {'id': 9, 'deal_id': 4, 'due_date': '2026-06-04', 'note': 'confirm terms', 'status': 'open', 'rep_id': 3},
        "type": "Followup",
        "many": False,
    },
    "update_followup": {
        "lead": "the updated follow-up, shaped like:",
        "example": {'id': 9, 'deal_id': 4, 'due_date': '2026-06-04', 'note': 'confirm terms', 'status': 'done', 'rep_id': 3},
        "type": "Followup",
        "many": False,
    },
}
