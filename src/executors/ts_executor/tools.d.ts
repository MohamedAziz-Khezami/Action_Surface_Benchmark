// tools.d.ts — GENERATED, do not edit by hand.
// Run `python main.py gen-tools` to rebuild.
//
// Typed signatures for the CRM tools, compiled against the model's code by
// the TS executor. Generated from the same source as tools.json,
// tools_python.pyi and tools_js.js, so every surface is told exactly the
// same facts about every tool.

interface Rep {
  id: number;
  name: string;
  email: string;
  team: string;
  active: number;
}

interface Contact {
  id: number;
  name: string;
  email: string;
  phone: string | null;
  company: string | null;
  rep_id: number;
  created_at: string;
}

interface Lead {
  id: number;
  contact_id: number;
  source: "webform" | "referral" | "event" | "cold_call" | "inbound_email";
  score: number;
  status: "new" | "qualified" | "unqualified" | "converted";
  rep_id: number;
  created_at: string;
}

interface Deal {
  id: number;
  lead_id: number;
  name: string;
  stage: "prospecting" | "qualification" | "proposal" | "negotiation" | "closing" | "won" | "lost";
  value: number;
  currency: string;
  close_date: string | null;
  rep_id: number;
  created_at: string;
}

interface Activity {
  id: number;
  deal_id: number | null;
  contact_id: number | null;
  type: "call" | "email" | "meeting" | "note";
  subject: string;
  ts: string;
  rep_id: number;
}

interface Followup {
  id: number;
  deal_id: number;
  due_date: string;
  note: string | null;
  status: "open" | "done";
  rep_id: number;
}

interface ToolsInterface {
  /**
   * tools.list_reps()
   * List every sales rep.
   *
   * Arguments: none
   *
   * Returns: a list of reps, each shaped like:
   * {"id": 3, "name": "Priya Chen", "email": "priya.chen@company.example", "team": "East", "active": 1}
   */
  list_reps(): Promise<Rep[]>;

  /**
   * tools.find_contacts({name: "Alice", email: null, company: "Wonka", rep_id: null})
   * Search contacts by name, email, company, or rep. All arguments are optional — omit any you don't need.
   *
   * Arguments:
   *   name (string)    — optional — case-insensitive partial match on the contact's name
   *   email (string)   — optional — exact match on the contact's email
   *   company (string) — optional — exact match on the contact's company
   *   rep_id (number)  — optional — only return contacts owned by this rep's id
   *
   * Returns: a list of contacts, each shaped like:
   * {"id": 7, "name": "Alice Nakamura", "email": "alice.nakamura@wonka.example", "phone": "+1-555-3362", "company": "Wonka", "rep_id": 6, "created_at": "2026-01-14"}
   */
  find_contacts(args?: { name?: string; email?: string; company?: string; rep_id?: number }): Promise<Contact[]>;

  /**
   * tools.get_contact({id: 7})
   * Fetch one contact by id.
   *
   * Arguments:
   *   id (number) — required — the contact's id
   *
   * Returns: one contact, shaped like:
   * {"id": 7, "name": "Alice Nakamura", "email": "alice.nakamura@wonka.example", "phone": "+1-555-3362", "company": "Wonka", "rep_id": 6, "created_at": "2026-01-14"}
   */
  get_contact(args: { id: number }): Promise<Contact>;

  /**
   * tools.find_leads({contact_id: 7, rep_id: null, status: "qualified", min_score: null})
   * Search leads by contact, rep, status, or minimum score. All arguments are optional — omit any you don't need.
   *
   * Arguments:
   *   contact_id (number) — optional — only return leads for this contact's id
   *   rep_id (number)     — optional — only return leads owned by this rep's id
   *   status (string)     — optional — only return leads with this status — one of: "new", "qualified", "unqualified", "converted"
   *   min_score (number)  — optional — only return leads with a score at or above this value
   *
   * Returns: a list of leads, each shaped like:
   * {"id": 12, "contact_id": 7, "source": "referral", "score": 72, "status": "qualified", "rep_id": 6, "created_at": "2026-01-20"}
   */
  find_leads(args?: { contact_id?: number; rep_id?: number; status?: "new" | "qualified" | "unqualified" | "converted"; min_score?: number }): Promise<Lead[]>;

  /**
   * tools.get_lead({id: 12})
   * Fetch one lead by id.
   *
   * Arguments:
   *   id (number) — required — the lead's id
   *
   * Returns: one lead, shaped like:
   * {"id": 12, "contact_id": 7, "source": "referral", "score": 72, "status": "qualified", "rep_id": 6, "created_at": "2026-01-20"}
   */
  get_lead(args: { id: number }): Promise<Lead>;

  /**
   * tools.get_deal({id: 4})
   * Fetch one deal by id.
   *
   * Arguments:
   *   id (number) — required — the deal's id
   *
   * Returns: one deal, shaped like:
   * {"id": 4, "lead_id": 12, "name": "Acme rollout", "stage": "proposal", "value": 45000.0, "currency": "USD", "close_date": "2026-06-01", "rep_id": 3, "created_at": "2026-01-15"}
   */
  get_deal(args: { id: number }): Promise<Deal>;

  /**
   * tools.find_deals({lead_id: null, stage: "proposal", rep_id: null, min_value: 1000})
   * Search deals by lead, stage, rep, or minimum value. All arguments are optional — omit any you don't need.
   *
   * Arguments:
   *   lead_id (number)   — optional — only return deals under this lead's id
   *   stage (string)     — optional — only return deals in this pipeline stage — one of: "prospecting", "qualification", "proposal", "negotiation", "closing", "won", "lost"
   *   rep_id (number)    — optional — only return deals owned by this rep's id
   *   min_value (number) — optional — only return deals worth at least this amount
   *
   * Returns: a list of deals, each shaped like:
   * {"id": 4, "lead_id": 12, "name": "Acme rollout", "stage": "proposal", "value": 45000.0, "currency": "USD", "close_date": "2026-06-01", "rep_id": 3, "created_at": "2026-01-15"}
   */
  find_deals(args?: { lead_id?: number; stage?: "prospecting" | "qualification" | "proposal" | "negotiation" | "closing" | "won" | "lost"; rep_id?: number; min_value?: number }): Promise<Deal[]>;

  /**
   * tools.get_activities({deal_id: 4, contact_id: null})
   * List activities for a deal or a contact. One of deal_id/contact_id is required (not both need to be set, but at least one must be).
   *
   * Arguments:
   *   deal_id (number)    — optional — only return activities on this deal's id
   *   contact_id (number) — optional — only return activities on this contact's id
   *
   * Returns: a list of activities, each shaped like:
   * {"id": 21, "deal_id": 4, "contact_id": 12, "type": "call", "subject": "pricing", "ts": "2026-02-01T12:00:00", "rep_id": 3}
   */
  get_activities(args?: { deal_id?: number; contact_id?: number }): Promise<Activity[]>;

  /**
   * tools.get_followups({deal_id: 4, rep_id: null, status: "open"})
   * Search follow-ups by deal, rep, or status. All arguments are optional — omit any you don't need.
   *
   * Arguments:
   *   deal_id (number) — optional — only return follow-ups on this deal's id
   *   rep_id (number)  — optional — only return follow-ups owned by this rep's id
   *   status (string)  — optional — only return follow-ups with this status — one of: "open", "done"
   *
   * Returns: a list of follow-ups, each shaped like:
   * {"id": 9, "deal_id": 4, "due_date": "2026-06-04", "note": "confirm terms", "status": "open", "rep_id": 3}
   */
  get_followups(args?: { deal_id?: number; rep_id?: number; status?: "open" | "done" }): Promise<Followup[]>;

  /**
   * tools.create_contact({name: "Bob Larsen", email: "bob.larsen@wonka.example", rep_id: 6, company: "Wonka", phone: "+1-555-8335"})
   * Create a new contact; fails if the email already exists.
   *
   * Arguments:
   *   name (string)    — required — the contact's full name
   *   email (string)   — required — must be unique across all contacts
   *   rep_id (number)  — required — the id of the rep who owns this contact
   *   company (string) — optional
   *   phone (string)   — optional
   *
   * Returns: the newly created contact, shaped like:
   * {"id": 60, "name": "Bob Larsen", "email": "bob.larsen@wonka.example", "phone": "+1-555-8335", "company": "Wonka", "rep_id": 6, "created_at": "2026-06-01"}
   */
  create_contact(args: { name: string; email: string; rep_id: number; company?: string; phone?: string }): Promise<Contact>;

  /**
   * tools.update_contact({id: 7, name: null, email: null, company: null, phone: "+1-555-9999", rep_id: null})
   * Update one or more fields on an existing contact. Only the fields you pass are changed.
   *
   * Arguments:
   *   id (number)      — required — the contact's id
   *   name (string)    — optional
   *   email (string)   — optional — must be unique across all contacts
   *   company (string) — optional
   *   phone (string)   — optional
   *   rep_id (number)  — optional — reassign this contact to a different rep
   *
   * Returns: the updated contact, shaped like:
   * {"id": 7, "name": "Alice Nakamura", "email": "alice.nakamura@wonka.example", "phone": "+1-555-9999", "company": "Wonka", "rep_id": 6, "created_at": "2026-01-14"}
   */
  update_contact(args: { id: number; name?: string; email?: string; company?: string; phone?: string; rep_id?: number }): Promise<Contact>;

  /**
   * tools.create_lead({contact_id: 7, source: "referral", score: 72, rep_id: null})
   * Create a new lead for a contact.
   *
   * Arguments:
   *   contact_id (number) — required — the contact this lead is for
   *   source (string)     — required — how the lead came in — one of: "webform", "referral", "event", "cold_call", "inbound_email"
   *   score (number)      — optional — defaults to 50 if omitted
   *   rep_id (number)     — optional — defaults to the contact's own rep if omitted
   *
   * Returns: the newly created lead, shaped like:
   * {"id": 12, "contact_id": 7, "source": "referral", "score": 72, "status": "new", "rep_id": 6, "created_at": "2026-06-01"}
   */
  create_lead(args: { contact_id: number; source: "webform" | "referral" | "event" | "cold_call" | "inbound_email"; score?: number; rep_id?: number }): Promise<Lead>;

  /**
   * tools.update_lead({id: 12, status: "qualified", score: null, source: "webform"})
   * Update a lead's status, score, and/or source. Only the fields you pass are changed.
   *
   * Arguments:
   *   id (number)     — required — the lead's id
   *   status (string) — optional — one of: "new", "qualified", "unqualified", "converted"
   *   score (number)  — optional
   *   source (string) — optional — one of: "webform", "referral", "event", "cold_call", "inbound_email"
   *
   * Returns: the updated lead, shaped like:
   * {"id": 12, "contact_id": 7, "source": "referral", "score": 72, "status": "qualified", "rep_id": 6, "created_at": "2026-01-20"}
   */
  update_lead(args: { id: number; status?: "new" | "qualified" | "unqualified" | "converted"; score?: number; source?: "webform" | "referral" | "event" | "cold_call" | "inbound_email" }): Promise<Lead>;

  /**
   * tools.create_deal({lead_id: 12, name: "Acme rollout", value: 45000, stage: "prospecting", close_date: null})
   * Create a new deal under a lead.
   *
   * Arguments:
   *   lead_id (number)    — required — the lead this deal is under
   *   name (string)       — required — a short label for the deal
   *   value (number)      — required — the deal's monetary value
   *   stage (string)      — optional — defaults to "prospecting" if omitted — one of: "prospecting", "qualification", "proposal", "negotiation", "closing", "won", "lost"
   *   close_date (string) — optional — expected close date, "YYYY-MM-DD"
   *
   * Returns: the newly created deal, shaped like:
   * {"id": 4, "lead_id": 12, "name": "Acme rollout", "stage": "prospecting", "value": 45000.0, "currency": "USD", "close_date": null, "rep_id": 6, "created_at": "2026-06-01"}
   */
  create_deal(args: { lead_id: number; name: string; value: number; stage?: "prospecting" | "qualification" | "proposal" | "negotiation" | "closing" | "won" | "lost"; close_date?: string }): Promise<Deal>;

  /**
   * tools.update_deal({id: 4, stage: "negotiation", value: null, close_date: null})
   * Update a deal's stage, value, and/or close date. Only the fields you pass are changed.
   *
   * Arguments:
   *   id (number)         — required — the deal's id
   *   stage (string)      — optional — one of: "prospecting", "qualification", "proposal", "negotiation", "closing", "won", "lost"
   *   value (number)      — optional
   *   close_date (string) — optional — "YYYY-MM-DD"
   *
   * Returns: the updated deal, shaped like:
   * {"id": 4, "lead_id": 12, "name": "Acme rollout", "stage": "negotiation", "value": 45000.0, "currency": "USD", "close_date": "2026-06-01", "rep_id": 3, "created_at": "2026-01-15"}
   */
  update_deal(args: { id: number; stage?: "prospecting" | "qualification" | "proposal" | "negotiation" | "closing" | "won" | "lost"; value?: number; close_date?: string }): Promise<Deal>;

  /**
   * tools.log_activity({type: "call", subject: "pricing", deal_id: 4, contact_id: null})
   * Log a call, email, meeting, or note on a deal or contact. At least one of deal_id/contact_id should be set; if you pass only deal_id, contact_id is filled in automatically from the deal's contact.
   *
   * Arguments:
   *   type (string)       — required — one of: "call", "email", "meeting", "note"
   *   subject (string)    — required — a short description of the activity
   *   deal_id (number)    — optional — the deal this activity is logged against
   *   contact_id (number) — optional — the contact this activity is logged against
   *
   * Returns: the newly created activity, shaped like:
   * {"id": 21, "deal_id": 4, "contact_id": 12, "type": "call", "subject": "pricing", "ts": "2026-06-01T12:00:00", "rep_id": 3}
   */
  log_activity(args: { type: "call" | "email" | "meeting" | "note"; subject: string; deal_id?: number; contact_id?: number }): Promise<Activity>;

  /**
   * tools.schedule_followup({deal_id: 4, due_date: "2026-06-04", note: "confirm terms"})
   * Schedule a follow-up on a deal.
   *
   * Arguments:
   *   deal_id (number)  — required — the deal this follow-up is on
   *   due_date (string) — required — "YYYY-MM-DD"
   *   note (string)     — optional
   *
   * Returns: the newly created follow-up, shaped like:
   * {"id": 9, "deal_id": 4, "due_date": "2026-06-04", "note": "confirm terms", "status": "open", "rep_id": 3}
   */
  schedule_followup(args: { deal_id: number; due_date: string; note?: string }): Promise<Followup>;

  /**
   * tools.update_followup({id: 9, status: "done", due_date: "2026-06-11", note: "confirm terms"})
   * Update a follow-up's status (e.g. mark done), due date, and/or note.
   *
   * Arguments:
   *   id (number)       — required
   *   status (string)   — optional — one of: "open", "done"
   *   due_date (string) — optional — "YYYY-MM-DD"
   *   note (string)     — optional
   *
   * Returns: the updated follow-up, shaped like:
   * {"id": 9, "deal_id": 4, "due_date": "2026-06-04", "note": "confirm terms", "status": "done", "rep_id": 3}
   */
  update_followup(args: { id: number; status?: "open" | "done"; due_date?: string; note?: string }): Promise<Followup>;
}
declare const tools: ToolsInterface;
