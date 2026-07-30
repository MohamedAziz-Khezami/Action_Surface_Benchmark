# Which task types this tier draws from. Everything else about a task
# lives INSIDE the template file: templates/expert/<name>.yaml.
TIER_CONFIG = {
    "templates": ["decide_by_deal_value", "update_every_matching_deal",
                   "triage_each_followup", "find_deal_via_chain",
                   "reassign_contacts"],
}
