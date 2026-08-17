# test_batching_cap.py — the batching ablation (--max-tool-calls-per-exec).
#
# The ablation's whole value rests on the cap being real and symmetric: real,
# because a cap that let calls through would produce a false "batching doesn't
# matter" result; symmetric, because if it bound harder on one language than
# another, the surfaces would no longer be comparable and the ablation would
# measure an implementation accident instead of batching.
from __future__ import annotations

import json

import pytest

from cli import parse_args
from src.agent import prompts
from src.executors.python_executor.tools_client import ToolCallLimitExceeded, Tools
from src.meter.meter import _categorize_error

TASK = {"task_id": "t1", "answer_keys": ["contact_id"], "query": "q",
        "difficulty": "easy", "world_seed": 1}

CODE_SURFACES = ("python", "js", "ts")


# ── the flag ──────────────────────────────────────────────────────────────

def test_flag_defaults_to_uncapped():
    """Absent flag must mean "behave exactly as before the ablation existed" —
    otherwise every historical run becomes incomparable to new ones."""
    args = parse_args(["run", "--models", "m"])
    assert args.max_tool_calls_per_exec is None


def test_flag_parses():
    assert parse_args(["run", "--models", "m", "--max-tool-calls-per-exec", "1"]
                       ).max_tool_calls_per_exec == 1


# ── the prompt half of the contract ───────────────────────────────────────

@pytest.mark.parametrize("surface", CODE_SURFACES)
def test_cap_is_stated_in_the_prompt_for_every_code_surface(surface):
    """Enforcing silently would measure how models handle an undocumented
    failure, not whether batching is what helps them."""
    prompt = prompts.build_system_prompt(surface, "tool_call", TASK, 1)
    assert "at most one tool call" in prompt
    assert "tool_call_limit_exceeded" in prompt


@pytest.mark.parametrize("surface", CODE_SURFACES)
@pytest.mark.parametrize("mode", ["tool_call", "text_block"])
def test_cap_is_stated_in_both_interaction_modes(surface, mode):
    assert "at most" in prompts.build_system_prompt(surface, mode, TASK, 2)


@pytest.mark.parametrize("surface", CODE_SURFACES)
@pytest.mark.parametrize("mode", ["tool_call", "text_block"])
def test_uncapped_prompt_is_byte_identical_to_the_pre_ablation_prompt(surface, mode):
    """The uncapped arm must not pick up so much as a stray space, or the
    ablation would be confounded with a prompt change."""
    assert (prompts.build_system_prompt(surface, mode, TASK, None)
            == prompts.build_system_prompt(surface, mode, TASK))


def test_json_mcp_prompt_never_mentions_the_cap():
    """json_mcp has no execute() to cap — it is already the unbatched baseline.
    Mentioning a cap it cannot obey would be a gratuitous prompt difference."""
    capped = prompts.build_system_prompt("json_mcp", "tool_call", TASK, 1)
    assert "at most" not in capped
    assert capped == prompts.build_system_prompt("json_mcp", "tool_call", TASK)


def test_cap_line_is_grammatical_at_one_and_at_many():
    assert "at most one tool call" in prompts._batching_cap_line(1)
    assert "at most 3 tool calls" in prompts._batching_cap_line(3)


def test_initial_messages_carry_the_cap():
    msgs = prompts.build_initial_messages("python", "tool_call", TASK, 1)
    assert "at most one tool call" in msgs[0]["content"]


# ── the enforcement half, Python ──────────────────────────────────────────

def test_python_allows_calls_up_to_the_cap_then_blocks(monkeypatch):
    tools = Tools("http://x")
    tools.call_limit = 2
    sent = []

    def fake_post(url, json=None, timeout=None):
        sent.append(url)

        class R:
            @staticmethod
            def json():
                return {"success": True, "data": {}}
        return R()

    monkeypatch.setattr("src.executors.python_executor.tools_client.requests.post", fake_post)
    tools.get_contact(contact_id="c1")
    tools.get_contact(contact_id="c2")
    with pytest.raises(ToolCallLimitExceeded) as e:
        tools.get_contact(contact_id="c3")
    # The blocked call must never have reached the tool-server: a cap enforced
    # after the fact would not restrict the agent's writes at all.
    assert len(sent) == 2
    assert e.value.code == "tool_call_limit_exceeded"


def test_python_uncapped_by_default(monkeypatch):
    tools = Tools("http://x")
    monkeypatch.setattr(
        "src.executors.python_executor.tools_client.requests.post",
        lambda url, json=None, timeout=None: type("R", (), {"json": staticmethod(lambda: {"success": True, "data": {}})}))
    for _ in range(50):
        tools.get_contact(contact_id="c")
    assert tools.call_count == 50


def test_blocked_call_does_not_increment_the_call_counter(monkeypatch):
    """tool_calls_made must count calls actually made, or the ablation's own
    efficiency numbers would be inflated by the calls it refused."""
    tools = Tools("http://x")
    tools.call_limit = 1
    monkeypatch.setattr(
        "src.executors.python_executor.tools_client.requests.post",
        lambda url, json=None, timeout=None: type("R", (), {"json": staticmethod(lambda: {"success": True, "data": {}})}))
    tools.get_contact(contact_id="c")
    with pytest.raises(ToolCallLimitExceeded):
        tools.get_contact(contact_id="c")
    assert tools.call_count == 1


# ── the enforcement half, JS/TS: same rule, same place ────────────────────

@pytest.mark.parametrize("surface", ["js", "ts"])
def test_js_and_ts_check_the_cap_before_issuing_the_request(surface):
    """Read as source rather than executed (no Node in the test env), but the
    ordering is the property that matters and it is visible statically: the
    limit check must precede both the counter bump and the fetch()."""
    from pathlib import Path
    src = (Path(__file__).parent.parent / "executors" / f"{surface}_executor"
           / "tools_client.js").read_text()
    check = src.index("counter.limit !== null")
    assert check < src.index("counter.count += 1")
    assert check < src.index("await fetch(")
    assert "tool_call_limit_exceeded" in src


@pytest.mark.parametrize("surface", ["js", "ts"])
def test_js_and_ts_default_the_limit_to_null(surface):
    from pathlib import Path
    src = (Path(__file__).parent.parent / "executors" / f"{surface}_executor"
           / "tools_client.js").read_text()
    assert "{ count: 0, limit: null }" in src


@pytest.mark.parametrize("surface", ["js", "ts"])
def test_js_and_ts_read_the_cap_off_each_request(surface):
    """Per-request, not per-container: an env var would mean the capped and
    uncapped arms ran different images, which is itself a confound."""
    from pathlib import Path
    src = (Path(__file__).parent.parent / "executors" / f"{surface}_executor"
           / "exec_server.js").read_text()
    assert "max_tool_calls: maxToolCalls" in src
    assert "toolCallCounter.limit = maxToolCalls ?? null;" in src


def test_python_exec_server_reads_the_cap_off_each_request():
    from pathlib import Path
    src = (Path(__file__).parent.parent / "executors" / "python_executor"
           / "exec_server.py").read_text()
    assert 'tools.call_limit = payload.get("max_tool_calls")' in src


# ── the wire format ───────────────────────────────────────────────────────

class _FakeEpisode:
    """Captures the /exec payload without Docker."""

    def __init__(self):
        self.payloads = []

    def post(self, payload):
        self.payloads.append(payload)


def test_uncapped_exec_omits_the_field_entirely(monkeypatch):
    """An uncapped run must put the identical request on the wire as it did
    before this flag existed, so old and new uncapped results stay comparable."""
    import src.docker_runner.episode as ep_mod

    captured = {}

    class R:
        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"ok": True, "tool_calls": 0}

    def fake_post(url, json=None, timeout=None):
        captured.update(json)
        return R()

    monkeypatch.setattr(ep_mod.requests, "post", fake_post)
    episode = object.__new__(ep_mod.Episode)
    episode.executor = object()
    episode.surface = "python"
    episode._executor_url = "http://x"

    episode.exec("1", "python")
    assert "max_tool_calls" not in captured

    captured.clear()
    episode.exec("1", "python", max_tool_calls=1)
    assert captured["max_tool_calls"] == 1


# ── the meter ─────────────────────────────────────────────────────────────

def test_cap_hit_is_not_counted_as_a_code_error():
    """A cap hit is the ablation working, not a defect. Bucketing it as a
    runtime error would make the capped arm look like it degraded code quality
    and would inflate `recovered` for every episode that simply continued."""
    assert _categorize_error({"code": "tool_call_limit_exceeded",
                               "name": "ToolCallLimitExceeded"}) == "cap"


def test_cap_hits_are_counted_and_kept_out_of_recovered():
    from src.meter.meter import EpisodeMeter
    m = EpisodeMeter("e", "m", "python", "tool_call", "t1", "easy", 1, 2, "tpl", "pat",
                     max_tool_calls_per_exec=1)
    m.record_exec_result(
        {"ok": False, "tool_calls": 1,
         "error": {"code": "tool_call_limit_exceeded", "name": "ToolCallLimitExceeded"}}, 0.1)
    row = m.finalize({"passed": True, "reasons": [], "checks": {"answer": True}})
    assert row["exec_cap_hit_count"] == 1
    assert row["runtime_error_count"] == 0
    assert row["max_tool_calls_per_exec"] == 1
    # `recovered` means the model recovered from its OWN mistake; a cap hit
    # isn't one, so a passing capped episode must not be scored as a recovery.
    assert row["recovered"] == 0


def test_uncapped_episode_records_a_blank_cap_and_zero_hits():
    from src.meter.meter import EpisodeMeter
    m = EpisodeMeter("e", "m", "python", "tool_call", "t1", "easy", 1, 2, "tpl", "pat")
    row = m.finalize({"passed": True, "reasons": [], "checks": {"answer": True}})
    assert row["max_tool_calls_per_exec"] is None
    assert row["exec_cap_hit_count"] == 0


def test_every_meter_field_is_a_csv_column():
    """A field the meter emits but the CSV never declares is silently dropped
    by DictWriter — the ablation would run and record nothing."""
    from main import CSV_FIELDS
    from src.meter.meter import EpisodeMeter
    m = EpisodeMeter("e", "m", "python", "tool_call", "t1", "easy", 1, 2, "tpl", "pat")
    row = m.finalize({"passed": True, "reasons": [], "checks": {}})
    missing = set(row) - set(CSV_FIELDS)
    assert not missing, f"meter emits columns the CSV drops: {sorted(missing)}"


def test_execute_tool_schema_is_unchanged_by_the_cap():
    """The cap travels in the prompt, not in execute()'s JSON schema. Changing
    the schema would alter the token count of the code surfaces' tool catalog
    and confound the cost comparison."""
    schema = json.dumps(prompts._TOOLS_JSON["execute"])
    assert "max_tool_calls" not in schema
