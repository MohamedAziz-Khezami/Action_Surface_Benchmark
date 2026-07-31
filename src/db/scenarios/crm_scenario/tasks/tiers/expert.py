# Which task types this tier draws from. Everything else about a task
# lives INSIDE the template file: templates/expert/<name>.yaml.
TIER_CONFIG = {
    "templates": ["decide_by_deal_value", "update_every_matching_deal",
                   "triage_each_followup", "find_deal_via_chain",
                   "reassign_contacts", "qualify_new_leads",
                   "reschedule_overdue_followups", "increment_lead_scores",
                   "disqualify_low_score_leads",
                   "schedule_followup_on_each_open_deal"],
}
