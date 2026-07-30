# test_tool_parity.py — the guard on this benchmark's central claim.
#
# The whole design rests on one premise: the ONLY thing that differs between
# surfaces is how the model is allowed to act. If json_mcp's schemas and the
# code-mode references ever describe a tool differently, that premise is
# silently false — no crash, no error, just a comparison that is measuring
# documentation quality alongside action encoding.
#
# The four documents are generated from one source, so they cannot drift
# apart on their own. What these tests defend against is the two ways drift
# can still be introduced: someone hand-editing a generated file, and someone
# adding a tool without documenting what it returns.
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.tool_server.schema_gen import (
    build_tools_json,
    check_all,
    iter_tool_specs,
    render_prose_doc,
    render_ts_decl,
    JS,
    PYTHON,
)

REPO_ROOT = Path(__file__).parent.parent.parent
SPECS = iter_tool_specs()
TOOLS_JSON = {t["function"]["name"]: t["function"] for t in build_tools_json()["crm_tools"]}
PROSE_DOCS = {"python": render_prose_doc(PYTHON), "js": render_prose_doc(JS), "ts": render_ts_decl()}


def test_generated_documents_are_current():
    """Every generated file on disk matches what the generator produces.

    Fails if a tool document was hand-edited, or a tool changed without
    `python main.py gen-tools` being re-run."""
    stale = check_all(str(REPO_ROOT))
    assert not stale, (
        "out of date — run `python main.py gen-tools`:\n  " + "\n  ".join(stale))


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.name)
def test_every_tool_appears_on_every_surface(spec):
    assert spec.name in TOOLS_JSON, f"{spec.name} missing from tools.json"
    for surface, doc in PROSE_DOCS.items():
        assert spec.name in doc, f"{spec.name} missing from the {surface} document"


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.name)
def test_description_is_identical_on_every_surface(spec):
    """A tool must not sell itself differently to different surfaces.

    This regressed once already: 9 of 18 tools told code-mode "All arguments
    are optional" while json_mcp was never told."""
    assert spec.description in TOOLS_JSON[spec.name]["description"]
    for surface, doc in PROSE_DOCS.items():
        assert spec.description in doc, f"{spec.name}: description differs on {surface}"


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.name)
def test_arguments_match_the_pydantic_model(spec):
    """The schema shown to the model is the one the server actually validates."""
    params = TOOLS_JSON[spec.name]["parameters"]
    fields = spec.args_model.model_fields if spec.args_model else {}
    assert list(params["properties"]) == list(fields), f"{spec.name}: argument set/order"
    expected_required = [n for n, f in fields.items() if f.is_required()]
    assert params["required"] == expected_required, f"{spec.name}: required set"


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.name)
def test_enum_members_reach_every_surface(spec):
    """A closed set of values is only useful if every surface is told it."""
    for arg, schema in TOOLS_JSON[spec.name]["parameters"]["properties"].items():
        for member in schema.get("enum", []):
            for surface, doc in PROSE_DOCS.items():
                assert f'"{member}"' in doc, (
                    f"{spec.name}.{arg}: enum member {member!r} missing from {surface}")


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.name)
def test_return_shape_reaches_every_surface(spec):
    """Knowing a result's fields without calling the tool is an advantage.

    It used to be a code-mode-only advantage — json_mcp had to spend a turn
    discovering what a tool returned. Every surface is told now, so the test
    holds the line."""
    assert "Returns:" in TOOLS_JSON[spec.name]["description"], (
        f"{spec.name}: json_mcp is not told what this tool returns")
    for surface, doc in PROSE_DOCS.items():
        block = _block_for(spec.name, surface, doc)
        assert "Returns:" in block, f"{spec.name}: {surface} is not told what this returns"


def test_no_tool_is_untyped_in_typescript():
    """`Promise<unknown>` means a missing RETURN_DOCS entry silently switched
    off type-checking for that tool's results."""
    untyped = re.findall(r"^  (\w+)\(.*\): Promise<unknown>;", PROSE_DOCS["ts"], re.M)
    assert not untyped, f"tools with no typed return: {untyped}"


def test_argument_prose_is_shown_to_all_or_to_none():
    """An argument explained to one surface must be explained to every surface."""
    gaps = []
    for spec in SPECS:
        for arg, schema in TOOLS_JSON[spec.name]["parameters"]["properties"].items():
            documented_in_mcp = bool(schema.get("description"))
            for surface, doc in PROSE_DOCS.items():
                block = _block_for(spec.name, surface, doc)
                m = re.search(rf"^\s*\*?\s*{arg} \(\w+\)\s+— (?:required|optional)"
                              rf"(?:\s+— (.+))?$", block, re.M)
                prose = (m.group(1) if m and m.group(1) else "")
                prose = re.sub(r"^one of:.*$", "", prose).strip()
                prose = re.sub(r"\s*—\s*one of:.*$", "", prose).strip()
                if bool(prose) != documented_in_mcp:
                    gaps.append(f"{spec.name}.{arg}: {surface}={bool(prose)} json_mcp={documented_in_mcp}")
    assert not gaps, "argument documented to some surfaces but not others:\n  " + "\n  ".join(gaps)


def test_execute_tool_offers_only_runnable_languages():
    """The `lang` enum comes from the executor images, so a surface can never
    be advertised to the model without a container to run it."""
    from config import EXECUTOR_IMAGES
    execute = build_tools_json()["execute"]["function"]
    assert execute["name"] == "execute"
    assert execute["parameters"]["properties"]["lang"]["enum"] == list(EXECUTOR_IMAGES)


def test_example_row_agrees_with_the_typescript_interface():
    """Both describe the SAME result, to different surfaces.

    python/js/json_mcp learn a tool's result shape from the example row; the
    TS surface learns it from the interface. If the two drift apart, those
    surfaces are told different things about the same return value — the exact
    class of asymmetry this benchmark exists to avoid."""
    from src.tool_server.tool_docs import RESULT_TYPES, RETURN_DOCS

    problems = []
    for tool, returns in RETURN_DOCS.items():
        interface = RESULT_TYPES[returns["type"]]
        example = returns["example"]
        if set(example) != set(interface):
            problems.append(
                f"{tool}: example row fields {sorted(set(example) ^ set(interface))} "
                f"differ from interface {returns['type']}")
            continue
        for field, value in example.items():
            declared = interface[field]
            matches = (
                (isinstance(value, bool) and "boolean" in declared)
                or (isinstance(value, (int, float)) and not isinstance(value, bool)
                    and "number" in declared)
                or (isinstance(value, str) and ("string" in declared or '"' in declared))
                or (value is None and "null" in declared))
            if not matches:
                problems.append(f"{tool}.{field}: example {value!r} vs declared {declared!r}")
    assert not problems, "example rows disagree with their TS interfaces:\n  " + "\n  ".join(problems)


def test_example_rows_use_values_that_can_actually_occur():
    """A documented example must show data a generated world could contain.

    The rep example once read `"team": "Enterprise"` while every world draws
    teams from ["East", "West", "North", "South"] — a value no task could ever
    produce, shown in the one place the model is told what a rep looks like.
    Example ROWS are curated by hand for readability (they tell one coherent
    story: contact 7 is Alice, lead 12 is hers, deal 4 is under that lead), so
    they are not generated — but every closed-set field in them is checked
    against the same authority the world generator uses."""
    import typing

    from src.db.scenarios.crm_scenario import pools
    from src.tool_server import models as M
    from src.tool_server.tool_docs import RETURN_DOCS

    def members(literal_alias):
        return list(typing.get_args(literal_alias))

    # (result type, field) -> the values that field may legally take.
    # Explicit rather than inferred from field names: a rename should make this
    # map fail loudly, not quietly stop covering the field.
    closed_sets = {
        ("Rep", "team"): pools.TEAMS,
        ("Lead", "source"): members(M.LeadSource),
        ("Lead", "status"): members(M.LeadStatus),
        ("Deal", "stage"): members(M.Stage),
        ("Deal", "currency"): ["USD"],          # crm_db.py: DEFAULT 'USD'
        ("Activity", "type"): members(M.ActivityType),
        ("Followup", "status"): members(M.FollowupStatus),
    }

    problems = []
    for tool, returns in RETURN_DOCS.items():
        for field, value in returns["example"].items():
            allowed = closed_sets.get((returns["type"], field))
            if allowed is not None and value not in allowed:
                problems.append(
                    f"{tool}: {returns['type']}.{field} = {value!r}, but only {allowed} can occur")
    assert not problems, "example rows show impossible values:\n  " + "\n  ".join(problems)


def test_every_argument_is_represented_on_the_signature_line():
    """Every argument must be a deliberate choice, not an oversight.

    NOTE a `None` in a signature is NOT a gap — it is a teaching device. The
    hand-written docs wrote `find_contacts(name="Alice", email=None,
    company="Wonka", rep_id=None)` on purpose, to show that optional arguments
    can be passed or omitted freely. So what counts as missing is an argument
    absent from ARG_EXAMPLES altogether, with no enum to fall back on: that one
    renders as None by accident rather than by intent.

    Deliberately a test rather than a hard generation error, unlike the missing
    RETURN_DOCS guard: a missing return shape costs the TS surface its
    type-checking, while an uncurated example only makes one line read worse."""
    from src.tool_server.tool_docs import ARG_EXAMPLES

    missing = []
    for spec in SPECS:
        curated = ARG_EXAMPLES.get(spec.name, {})
        for arg, schema in TOOLS_JSON[spec.name]["parameters"]["properties"].items():
            if arg not in curated and "enum" not in schema:
                missing.append(f"{spec.name}.{arg}")
    assert not missing, (
        "arguments with no curated example and no enum to fall back on — they "
        "render as None by accident. Add a value (or an explicit None, if "
        "showing it omitted is the point) to ARG_EXAMPLES in tool_docs.py:\n  "
        + "\n  ".join(missing))


def test_tool_docs_has_no_stale_entries():
    """Prose keyed to a tool or argument that no longer exists.

    Harmless at runtime — it is simply never read — which is why it rots
    silently and then misleads the next person editing the file."""
    from src.tool_server.tool_docs import ARG_DOCS, ARG_EXAMPLES, RESULT_TYPES, RETURN_DOCS

    by_name = {s.name: s for s in SPECS}
    stale = []
    for label, table in (("ARG_DOCS", ARG_DOCS), ("ARG_EXAMPLES", ARG_EXAMPLES),
                          ("RETURN_DOCS", RETURN_DOCS)):
        for tool in table:
            if tool not in by_name:
                stale.append(f"{label}[{tool!r}] — no such tool")
    for label, table in (("ARG_DOCS", ARG_DOCS), ("ARG_EXAMPLES", ARG_EXAMPLES)):
        for tool, args in table.items():
            if tool not in by_name:
                continue
            real = set(TOOLS_JSON[tool]["parameters"]["properties"])
            for arg in args:
                if arg not in real:
                    stale.append(f"{label}[{tool!r}][{arg!r}] — no such argument")
    for tool, returns in RETURN_DOCS.items():
        if returns.get("type") not in RESULT_TYPES:
            stale.append(f"RETURN_DOCS[{tool!r}].type={returns.get('type')!r} — no RESULT_TYPES entry")
    returned = {r.get("type") for r in RETURN_DOCS.values()}
    for name in RESULT_TYPES:
        if name not in returned:
            stale.append(f"RESULT_TYPES[{name!r}] — declared but no tool returns it")
    assert not stale, "stale tool_docs entries:\n  " + "\n  ".join(stale)


def test_tool_names_match_the_real_server_routes():
    server = (REPO_ROOT / "src" / "tool_server" / "server.py").read_text()
    routes = set(re.findall(r'operation_id="(\w+)"', server)) - {"mcp_http"}
    assert set(TOOLS_JSON) == routes


def _block_for(tool: str, surface: str, doc: str) -> str:
    """The slice of a prose document describing one tool, and ONLY that tool.

    The TS pattern matches JSDoc body lines (`   *`) rather than any line:
    a method declaration never starts that way, so the block cannot silently
    run backwards across its neighbours and pick up their prose."""
    # NOTE [^\n] rather than . throughout: these run under re.S, where a bare
    # `.` also matches newlines and turns the repetition into a backtracking bomb.
    if surface == "ts":
        pattern = rf"  /\*\*\n(?:   \*[^\n]*\n)*?   \*/\n  {tool}\([^\n]*\n"
    else:
        pattern = rf"^tools\.{tool}\(.*?(?=\n\ntools\.|\Z)"
    m = re.search(pattern, doc, re.M | re.S)
    assert m, f"no block for {tool} in {surface}"
    return m.group(0)
