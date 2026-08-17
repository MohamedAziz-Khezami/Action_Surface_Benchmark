# prompts.py — builds the system prompt and `tools=` parameter for one
# episode, branching on (surface, interaction_mode). Pure functions, no
# model/Docker dependency, so fully testable on their own.
from __future__ import annotations

import json
from pathlib import Path

from src.db.scenarios.crm_scenario.crm_db import SIM_TODAY

_TOOLS_JSON = json.loads((Path(__file__).parent / "tools.json").read_text())

# Each code-mode surface gets its OWN hand-written tool reference, in that
# language's own native style (real Python kwargs signatures, real JSDoc,
# real TS types) — not one shared document. Reusing a single TS-shaped
# document across all three previously misled a real model (gemma4) into
# writing tools.find_deals(args={...}) for Python, which
# tool_server/models.py's extra="forbid" would reject outright.
_TOOLS_DOC_BY_SURFACE = {
    "python": (Path(__file__).parent / "tools_python.pyi").read_text(),
    "js": (Path(__file__).parent / "tools_js.js").read_text(),
    "ts": (Path(__file__).parent.parent / "executors" / "ts_executor" / "tools.d.ts").read_text(),
}


def build_final_answer_tool(task: dict) -> dict:
    """final_answer's schema depends on the task's own answer_keys, so unlike
    the 17 CRM tools + execute (fixed, hand-written in tools.json), this is
    built fresh per task."""
    properties = {key: {"type": "string"} for key in task["answer_keys"]}
    return {
        "type": "function",
        "function": {
            "name": "final_answer",
            "description": "Submit your final answer for this task.",
            "parameters": {"type": "object", "properties": properties,
                            "required": task["answer_keys"]},
        },
    }


def build_tools_param(surface: str, interaction_mode: str, task: dict) -> list[dict] | None:
    """Returns the `tools=` argument for client.complete(), or None for
    text_block mode (which uses no structured tools at all)."""
    if interaction_mode == "text_block":
        return None
    final_answer = build_final_answer_tool(task)
    if surface == "json_mcp":
        return _TOOLS_JSON["crm_tools"] + [final_answer]
    return [_TOOLS_JSON["execute"], final_answer]


_LOOKUP_DISCIPLINE = (
    "Never guess or fabricate an id — every id you use (in an action or in "
    "your final answer) must come from a tool result you actually received. "
    "Entities are related in a chain: a contact belongs to a company, a "
    "lead belongs to a contact, a deal belongs to a lead, and activities/"
    "follow-ups belong to a deal or contact. If the task refers to a "
    "specific existing record (e.g. \"the overdue follow-up on the Acme "
    "deal\"), search/look it up through that chain first — do not create a "
    "new record as a substitute when a lookup comes up empty; broaden or "
    "retry the search instead. Before calling final_answer, double-check "
    "the id(s) you're reporting actually match the entity the task "
    "described, not just any record you happened to touch."
)


def _batching_cap_line(max_tool_calls: int | None) -> str:
    """The batching ablation's instruction to the model.

    The cap has to be STATED, not merely enforced. Enforcing it silently would
    make the ablation measure how models cope with an undocumented failure —
    every block would run, hit the wall, and error — instead of what it is meant
    to isolate: whether code-mode's advantage comes from batching many calls
    into one block, or from expressing the plan as code at all. A model told the
    rule can comply, so the capped arm differs from the uncapped arm in batching
    only, which is the whole point of the comparison."""
    if max_tool_calls is None:
        return ""
    calls = "one tool call" if max_tool_calls == 1 else f"{max_tool_calls} tool calls"
    return (
        f" IMPORTANT: each execute() call may make at most {calls}. A further "
        "call in the same block fails with tool_call_limit_exceeded and is not "
        "performed. Return the results you have and continue in the next "
        "execute() call. You may make as many execute() calls as you need.")


def build_system_prompt(surface: str, interaction_mode: str, task: dict,
                        max_tool_calls_per_exec: int | None = None) -> str:
    answer_keys = ", ".join(task["answer_keys"])

    today_line = f"Today's date is {SIM_TODAY}."

    if surface == "json_mcp":
        return (
            "You are solving a CRM task. "
            f"{today_line} "
            "Use the provided tools to look up and "
            "modify data as needed. "
            f"{_LOOKUP_DISCIPLINE} "
            "When you have the answer, call final_answer "
            f"with these fields: {answer_keys}."
        )

    tools_doc = _TOOLS_DOC_BY_SURFACE[surface]
    # json_mcp returns above and never sees this: it has no execute() to cap,
    # and one call per tool call is already its native behaviour — it IS the
    # unbatched baseline the capped code arms are being pushed toward.
    cap_line = _batching_cap_line(max_tool_calls_per_exec)

    if interaction_mode == "tool_call":
        return (
            f"You solve CRM tasks by writing {surface} code. {today_line} "
            f"Call the `execute` "
            f"tool with your code and lang='{surface}' to run it — always use "
            f"lang='{surface}', never any other value. Inside your code, a `tools` "
            "object is available with one method per CRM tool. Its available "
            f"methods:\n\n{tools_doc}\n\n"
            f"{_LOOKUP_DISCIPLINE}{cap_line} "
            "When you have the answer, call the separate final_answer tool "
            f"with these fields: {answer_keys}. final_answer is its own tool "
            "call, made the same way you call execute — it is not a method "
            "on `tools` and must never be written inside your executed code."
        )

    # text_block
    return (
        f"You solve CRM tasks by writing {surface} code in a fenced "
        f"```{surface} block. {today_line} Inside your code, a `tools` object is available "
        f"with one method per CRM tool. Its available methods:\n\n{tools_doc}\n\n"
        f"{_LOOKUP_DISCIPLINE}{cap_line} "
        "When you have solved the task, write the marker FINAL_ANSWER followed "
        "by a ```json code block containing an object with these exact keys: "
        f"{answer_keys}."
    )


def build_initial_messages(surface: str, interaction_mode: str, task: dict,
                           max_tool_calls_per_exec: int | None = None) -> list[dict]:
    return [
        {"role": "system", "content": build_system_prompt(
            surface, interaction_mode, task, max_tool_calls_per_exec)},
        {"role": "user", "content": task["query"]},
    ]
