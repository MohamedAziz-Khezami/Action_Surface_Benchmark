# Which task types this tier draws from. Everything else about a task
# (action count, distractors, phrasings) lives INSIDE the template file:
# templates/medium/<name>.yaml — each tier owns self-contained copies.
TIER_CONFIG = {
    "templates": ["act_on_a_deal", "act_on_a_followup", "act_on_a_lead",
                   "sum_pipeline_with_distractor", "sum_deals_in_stages",
                   "followups_due_within_window"],
}
