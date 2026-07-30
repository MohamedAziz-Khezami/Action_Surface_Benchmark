# schema_gen.py — generates the per-surface tool documentation from ONE source.
#
# WHY THIS EXISTS
# ---------------
# This benchmark's whole claim is that the ONLY thing differing between
# surfaces is how the model is allowed to act. If json_mcp's tool schemas and
# code-mode's `tools` reference ever disagree about a tool's arguments, that
# claim is silently false and every comparison built on it is invalid — with no
# crash and no error to notice. Hand-maintaining the same 18 tools in four
# separate documents makes that drift a matter of time.
#
# So the four documents are generated instead, and the source they are
# generated from is the tool-server's own FastAPI app:
#
#   route.operation_id      -> the tool name
#   the handler's docstring -> the tool description
#   the args model          -> the argument names, types, and required-ness
#
# The server is what actually validates and executes calls, so deriving the
# documentation from it means the docs cannot describe a tool the server does
# not implement, and vice versa. Parity across surfaces stops being something
# tests hope for and becomes true by construction.
from __future__ import annotations

import inspect
import json
import typing
from dataclasses import dataclass

from pydantic import BaseModel

from config import EXECUTOR_IMAGES
from src.tool_server.tool_docs import ARG_DOCS, ARG_EXAMPLES, RESULT_TYPES, RETURN_DOCS

# Python scalar -> JSON Schema `type`. Anything not in here (a Literal, an
# Optional wrapper) is handled structurally by _json_schema_for below.
_JSON_TYPES: dict[type, str] = {str: "string", int: "integer", float: "number", bool: "boolean"}

# FastApiMCP.mount_http() adds its own route to the same app; it carries an
# operation_id like any other but is transport plumbing, not a CRM tool.
_NON_TOOL_OPERATION_IDS = frozenset({"mcp_http"})


@dataclass(frozen=True)
class ToolSpec:
    """One tool, as read off the live FastAPI app."""
    name: str
    description: str
    args_model: type[BaseModel] | None  # None for a no-argument tool (list_reps)


def _unwrap_optional(annotation):
    """`Optional[X]` (i.e. `Union[X, None]`) -> `X`; anything else unchanged.

    JSON Schema expresses optionality by omission from `required`, not in the
    type itself, so the None arm is dropped rather than encoded."""
    if typing.get_origin(annotation) is typing.Union:
        non_none = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(non_none) == 1:
            return non_none[0]
    return annotation


def _json_schema_for(annotation) -> dict:
    """One field's annotation -> its JSON Schema fragment."""
    annotation = _unwrap_optional(annotation)
    if typing.get_origin(annotation) is typing.Literal:
        # Literal["open", "done"] is a closed set of values — the enum is the
        # whole point of declaring it, so it must survive into the schema. The
        # `type` is derived from the members rather than assumed to be string:
        # a Literal[1, 2] would otherwise emit type="string" alongside integer
        # members, a self-contradictory schema that nothing would flag.
        members = list(typing.get_args(annotation))
        member_types = {type(m) for m in members}
        if len(member_types) != 1:
            raise TypeError(
                f"Literal with mixed member types {member_types!r}: JSON Schema "
                f"needs one `type` for the whole enum")
        json_type = _JSON_TYPES.get(member_types.pop())
        if json_type is None:
            raise TypeError(f"no JSON Schema mapping for Literal members of {annotation!r}")
        return {"type": json_type, "enum": members}
    json_type = _JSON_TYPES.get(annotation)
    if json_type is None:
        raise TypeError(f"no JSON Schema mapping for annotation {annotation!r}")
    return {"type": json_type}


def _parameters_schema(args_model: type[BaseModel] | None, tool_name: str) -> dict:
    """An args model -> the OpenAI-style `parameters` object.

    Field declaration order is preserved (`model_fields` is ordered), so the
    generated document reads in the same order the model was written in.

    Each property carries its prose description, so a json_mcp model is told
    what an argument MEANS and not merely its type — the same thing the
    code-mode surfaces have always been told."""
    if args_model is None:
        return {"type": "object", "properties": {}, "required": []}
    arg_docs = ARG_DOCS.get(tool_name, {})
    properties, required = {}, []
    for field_name, field in args_model.model_fields.items():
        schema = _json_schema_for(field.annotation)
        description = arg_docs.get(field_name)
        if description:
            schema["description"] = description
        properties[field_name] = schema
        if field.is_required():
            required.append(field_name)
    return {"type": "object", "properties": properties, "required": required}


def _description_with_returns(spec: ToolSpec) -> str:
    """The tool description plus what it hands back.

    JSON Schema function-tools have nowhere structured to put a return shape,
    so it is appended to the description — the only channel a json_mcp model
    has. Without this it would have to spend a turn calling the tool just to
    discover which fields the result has, an asymmetry the code-mode surfaces
    never faced."""
    returns = RETURN_DOCS.get(spec.name)
    if not returns:
        return spec.description
    return (f"{spec.description}\n\n"
            f"Returns: {returns['lead']}\n{json.dumps(returns['example'])}")


def _args_model_of(endpoint) -> type[BaseModel] | None:
    """The Pydantic model a route handler takes, or None if it takes nothing.

    `server.py` uses `from __future__ import annotations`, so its annotations
    are strings at runtime; get_type_hints() resolves them against the module's
    own globals (where the models are already imported)."""
    hints = typing.get_type_hints(endpoint)
    for name, hint in hints.items():
        if name == "return":
            continue
        if isinstance(hint, type) and issubclass(hint, BaseModel):
            return hint
    return None


def iter_tool_specs() -> list[ToolSpec]:
    """Every CRM tool the tool-server actually serves, in route order."""
    from src.tool_server.server import app  # imported lazily: generation-time only

    specs = []
    for route in app.routes:
        operation_id = getattr(route, "operation_id", None)
        if not operation_id or operation_id in _NON_TOOL_OPERATION_IDS:
            continue
        description = inspect.getdoc(route.endpoint)
        if not description:
            raise ValueError(
                f"tool {operation_id!r} has no docstring — the docstring IS the "
                f"tool description shown to the model, so it cannot be omitted")
        specs.append(ToolSpec(name=operation_id, description=description,
                              args_model=_args_model_of(route.endpoint)))
    _assert_documented(specs)
    return specs


def _assert_documented(specs: list[ToolSpec]) -> None:
    """Every tool must have a RETURN_DOCS entry.

    Adding a route without one still generates a CONSISTENT set of documents —
    every surface is equally uninformed, so the comparison stays fair — but the
    new tool silently loses its return shape everywhere, and the TS surface
    degrades to `Promise<unknown>`, which switches off type-checking on that
    tool's results with no error. Consistency is guaranteed by construction;
    completeness is not, so it is asserted here instead."""
    undocumented = [s.name for s in specs if s.name not in RETURN_DOCS]
    if undocumented:
        raise ValueError(
            f"tool(s) {undocumented} have no RETURN_DOCS entry in tool_docs.py. "
            f"Add one (lead / example / type / many) so every surface can be told "
            f"what the tool returns — without it the TS surface falls back to "
            f"Promise<unknown> and loses type-checking on the result.")


def to_openai_tool(spec: ToolSpec) -> dict:
    """One ToolSpec -> one entry in the OpenAI/MCP-style `tools` array."""
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": _description_with_returns(spec),
            "parameters": _parameters_schema(spec.args_model, spec.name),
        },
    }


def build_execute_tool() -> dict:
    """The `execute` tool code-mode surfaces call instead of the CRM tools.

    Not derived from the tool-server (it is the harness's own affordance), but
    its `lang` enum IS derived from which executor images exist, so a surface
    can never be offered to the model without a container to run it."""
    return {
        "type": "function",
        "function": {
            "name": "execute",
            "description": ("Run a block of code against the CRM tools. `tools` is "
                            "available in scope with one method per CRM tool."),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "The code to run."},
                    "lang": {"type": "string", "enum": list(EXECUTOR_IMAGES)},
                },
                "required": ["code", "lang"],
            },
        },
    }


def build_tools_json() -> dict:
    """The whole `tools.json` document."""
    return {
        "crm_tools": [to_openai_tool(spec) for spec in iter_tool_specs()],
        "execute": build_execute_tool(),
    }


# ── the code-mode prose references ──────────────────────────────────────────
#
# The Python and JS documents differ ONLY in language dialect: how a call is
# written, what the scalar types are called, and how "no value" is spelled.
# Everything a model actually learns from them — descriptions, argument
# meanings, return shapes — comes from the same source as tools.json, so the
# three documents cannot disagree about a tool no matter how they are worded.


@dataclass(frozen=True)
class Dialect:
    """The surface-specific spelling of an otherwise identical document."""
    comment_prefix: str
    header: str
    types: dict[str, str]      # JSON Schema type -> this language's name for it
    null_literal: str
    call_style: str            # "kwargs" (python) | "object" (js)


PYTHON = Dialect(
    comment_prefix="#",
    header=("tools_python.pyi — GENERATED, do not edit by hand.\n"
            "Run `python main.py gen-tools` to rebuild.\n"
            "\n"
            "Reference for the `tools` object available in Python code-mode.\n"
            "Generated from the same source as tools.json and tools_js.js, so\n"
            "every surface is told exactly the same facts about every tool."),
    types={"string": "str", "integer": "int", "number": "float", "boolean": "bool"},
    null_literal="None",
    call_style="kwargs",
)

JS = Dialect(
    comment_prefix="//",
    header=("tools_js.js — GENERATED, do not edit by hand.\n"
            "Run `python main.py gen-tools` to rebuild.\n"
            "\n"
            "Reference for the `tools` object available in JS code-mode.\n"
            "Generated from the same source as tools.json and tools_python.pyi,\n"
            "so every surface is told exactly the same facts about every tool."),
    types={"string": "string", "integer": "number", "number": "number", "boolean": "boolean"},
    null_literal="null",
    call_style="object",
)


def _literal(value, dialect: Dialect) -> str:
    """A Python value -> how this language writes it."""
    if value is None:
        return dialect.null_literal
    return json.dumps(value)


def example_value_for(tool: str, arg: str, schema: dict):
    """The value shown for one argument on the signature line.

    A curated value wins. Failing that, an enum argument falls back to its
    first member — always a legal value, and it keeps a closed-set argument
    from being illustrated as `None`, which reads as though nothing sensible
    could go there. A plain string or number has no such fallback: inventing
    one would be guessing, so it stays None and a test flags it for curation."""
    curated = ARG_EXAMPLES.get(tool, {})
    if arg in curated:
        return curated[arg]
    if "enum" in schema:
        return schema["enum"][0]
    return None


def _signature(spec: ToolSpec, params: dict, dialect: Dialect) -> str:
    """`tools.find_deals(stage="proposal")` vs `tools.find_deals({stage: "proposal"})`.

    Uses the curated example values so the line reads like a real call a model
    might write, rather than a row of type placeholders."""
    props = params["properties"]
    if not props:
        return f"tools.{spec.name}()"
    parts = []
    for arg, schema in props.items():
        value = _literal(example_value_for(spec.name, arg, schema), dialect)
        parts.append(f"{arg}={value}" if dialect.call_style == "kwargs" else f"{arg}: {value}")
    inner = ", ".join(parts)
    return (f"tools.{spec.name}({inner})" if dialect.call_style == "kwargs"
            else f"tools.{spec.name}({{{inner}}})")


def _render_tool(spec: ToolSpec, dialect: Dialect) -> str:
    params = _parameters_schema(spec.args_model, spec.name)
    props, required = params["properties"], set(params["required"])
    lines = [_signature(spec, params, dialect), spec.description, ""]

    if not props:
        lines.append("Arguments: none")
    else:
        lines.append("Arguments:")
        # one aligned column, sized to the widest "name (type)" in THIS tool
        labels = {a: f"{a} ({dialect.types[s['type']]})" for a, s in props.items()}
        width = max(len(v) for v in labels.values())
        for arg, schema in props.items():
            bits = ["required" if arg in required else "optional"]
            if schema.get("description"):
                bits.append(schema["description"])
            if "enum" in schema:
                bits.append("one of: " + ", ".join(json.dumps(v) for v in schema["enum"]))
            lines.append(f"  {labels[arg]:<{width}} — " + " — ".join(bits))

    returns = RETURN_DOCS.get(spec.name)
    if returns:
        lines += ["", f"Returns: {returns['lead']}", json.dumps(returns["example"])]
    return "\n".join(lines)


def render_prose_doc(dialect: Dialect) -> str:
    """The whole tools_python.pyi / tools_js.js document."""
    header = "\n".join(f"{dialect.comment_prefix} {line}".rstrip()
                       for line in dialect.header.splitlines())
    blocks = [_render_tool(spec, dialect) for spec in iter_tool_specs()]
    return header + "\n\n" + "\n\n\n".join(blocks) + "\n"


def _repo_root():
    """This file is <root>/src/tool_server/schema_gen.py."""
    from pathlib import Path
    return Path(__file__).resolve().parents[2]


def generated_documents(root: str | None = None) -> dict:
    """Every generated tool document: path -> the content it SHOULD have.

    One definition shared by writing and checking, so `--check` can never
    disagree with what a write would actually produce.

    `root` defaults to the repo this module lives in, NOT the current working
    directory: resolving against the cwd made `--check` report every document
    as out of date when run from elsewhere, and would have made a plain
    generation write a phantom src/ tree wherever the shell happened to be."""
    from pathlib import Path

    base = Path(root) if root is not None else _repo_root()
    return {
        base / "src" / "agent" / "tools.json": json.dumps(build_tools_json(), indent=2) + "\n",
        base / "src" / "agent" / "tools_python.pyi": render_prose_doc(PYTHON),
        base / "src" / "agent" / "tools_js.js": render_prose_doc(JS),
        base / "src" / "executors" / "ts_executor" / "tools.d.ts": render_ts_decl(),
    }


def write_all(root: str | None = None) -> list[str]:
    """Regenerate every surface's tool document. Returns the paths written."""
    written = []
    for path, content in generated_documents(root).items():
        path.write_text(content)
        written.append(str(path))
    return written


def check_all(root: str | None = None) -> list[str]:
    """Paths whose on-disk content differs from what the generator produces.

    An empty list means every surface's document is current. A non-empty one
    means someone hand-edited a generated file (or changed a tool without
    regenerating) — which is exactly how one surface ends up describing a tool
    differently from the others."""
    stale = []
    for path, expected in generated_documents(root).items():
        if not path.exists() or path.read_text() != expected:
            stale.append(str(path))
    return stale


# ── the TypeScript declaration file ─────────────────────────────────────────
#
# tools.d.ts is the one generated document that is not merely read: the TS
# executor compiles the model's code against it with a real `ts.createProgram`
# pass, so a wrong type here becomes a compile error rather than bad advice.
# Its JSDoc is the *same* prose block the JS surface gets — rendered once,
# commented — so the TS surface cannot be told anything different from JS.

_TS_TYPES = {"string": "string", "integer": "number", "number": "number", "boolean": "boolean"}


def _ts_type(schema: dict) -> str:
    """A JSON Schema fragment -> its TypeScript type."""
    if "enum" in schema:
        return " | ".join(json.dumps(v) for v in schema["enum"])
    return _TS_TYPES[schema["type"]]


def _ts_args(params: dict) -> str:
    """The `args` parameter: omitted entirely, optional, or required.

    The object itself is optional only when every field in it is — matching
    how a caller would actually use it."""
    props, required = params["properties"], set(params["required"])
    if not props:
        return ""
    fields = "; ".join(
        f"{name}{'' if name in required else '?'}: {_ts_type(schema)}"
        for name, schema in props.items())
    return f"args{'' if required else '?'}: {{ {fields} }}"


def render_ts_decl() -> str:
    """The whole tools.d.ts document."""
    lines = [
        "// tools.d.ts — GENERATED, do not edit by hand.",
        "// Run `python main.py gen-tools` to rebuild.",
        "//",
        "// Typed signatures for the CRM tools, compiled against the model's code by",
        "// the TS executor. Generated from the same source as tools.json,",
        "// tools_python.pyi and tools_js.js, so every surface is told exactly the",
        "// same facts about every tool.",
        "",
    ]
    for name, fields in RESULT_TYPES.items():
        lines.append(f"interface {name} {{")
        lines += [f"  {field}: {ts_type};" for field, ts_type in fields.items()]
        lines += ["}", ""]

    lines.append("interface ToolsInterface {")
    blocks = []
    for spec in iter_tool_specs():
        params = _parameters_schema(spec.args_model, spec.name)
        # the JS surface's prose, verbatim, as JSDoc
        prose = _render_tool(spec, JS).splitlines()
        doc = ["  /**"] + [f"   * {line}".rstrip() for line in prose] + ["   */"]
        returns = RETURN_DOCS.get(spec.name)
        ret = f"{returns['type']}{'[]' if returns['many'] else ''}" if returns else "unknown"
        doc.append(f"  {spec.name}({_ts_args(params)}): Promise<{ret}>;")
        blocks.append("\n".join(doc))
    lines.append("\n\n".join(blocks))
    lines += ["}", "declare const tools: ToolsInterface;"]
    return "\n".join(lines) + "\n"
