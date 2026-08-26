# test_malformed_action.py — a model that emits an unusable action must be
# SCORED, not discarded.
#
# WHY THIS FILE EXISTS. llama-server answers a request whose output it cannot
# parse into a tool call with HTTP 500 ("...does not match the expected
# peg-native format"). The server is healthy; the model failed. Recording that
# as a model_api_error did three harmful things: it discarded the episode from
# the results, it counted toward main.py's circuit breaker (abandoning a model
# whose server was fine), and — worst — it deleted a surface-dependent failure
# mode from the study. json_mcp emits one structured call per action, 2-12 per
# episode across 17 tools with different argument shapes; a code surface emits
# 1-3 execute() wrappers of one fixed two-field shape. json_mcp is therefore
# far more exposed to this, so excluding these episodes computed its pass rate
# only over the episodes where it happened to stay grammatical.
from __future__ import annotations

import json

import pytest

from src.llm_clients.client import MalformedActionError, _is_malformed_output

PEG = ("Error code: 500 - {'error': {'code': 500, 'message': 'The model produced "
       "output that does not match the expected peg-native format', "
       "'type': 'server_error'}}")


class _Status(Exception):
    """Stands in for openai.APIStatusError, which carries a status_code."""

    def __init__(self, message, status_code):
        super().__init__(message)
        self.status_code = status_code


# ── classifying the 5xx ───────────────────────────────────────────────────

def test_the_observed_peg_error_is_recognised():
    assert _is_malformed_output(_Status(PEG, 500))


@pytest.mark.parametrize("message", [
    "500 - failed to parse tool call",
    "500 - output does not match the expected format",
    "500 - PEG-NATIVE parse failure",          # case-insensitive
])
def test_other_phrasings_of_the_same_failure_are_recognised(message):
    assert _is_malformed_output(_Status(message, 500))


@pytest.mark.parametrize("message,status", [
    ("Internal server error", 500),            # a real outage, no parse marker
    ("Service Unavailable", 503),              # server still loading
    ("Bad gateway", 502),
    ("does not match the expected format", 400),   # 4xx is a request problem
])
def test_a_genuine_server_fault_is_NOT_swallowed(message, status):
    """The circuit breaker exists to stop a dead server eating the run. If an
    outage were misread as a model failure the breaker would never fire and
    every remaining episode would buy another timeout."""
    assert not _is_malformed_output(_Status(message, status))


def test_an_exception_with_no_status_is_not_a_model_failure():
    assert not _is_malformed_output(RuntimeError("Connection error."))


def test_connection_error_stays_an_api_error():
    """The other failure actually seen in the fleet. A dead llama-server must
    keep tripping the breaker — that is the whole point of the breaker."""
    assert not _is_malformed_output(_Status("Connection error.", None))


# ── the client raises the right thing ─────────────────────────────────────

class _FakeCompletions:
    def __init__(self, exc=None, tool_args=None):
        self._exc, self._tool_args = exc, tool_args

    def create(self, **kwargs):
        if self._exc:
            raise self._exc

        class _Fn:
            name, arguments = "find_deals", self._tool_args

        class _TC:
            id, function = "call_1", _Fn()

        class _Msg:
            content, tool_calls = "", [_TC()]

        class _Usage:
            prompt_tokens = completion_tokens = 1

        class _Choice:
            message = _Msg()

        class _Resp:
            choices, usage = [_Choice()], _Usage()
        return _Resp()


def _client_with(exc=None, tool_args=None):
    from src.llm_clients.client import OpenAICompatibleClient
    c = object.__new__(OpenAICompatibleClient)
    c._model_id = "m"
    c._client = type("C", (), {"chat": type("Ch", (), {"completions": _FakeCompletions(exc, tool_args)})()})()
    return c


def test_client_converts_the_peg_500_into_a_malformed_action(monkeypatch):
    import openai
    monkeypatch.setattr(openai, "APIStatusError", _Status, raising=False)
    with pytest.raises(MalformedActionError):
        _client_with(exc=_Status(PEG, 500)).complete([{"role": "user", "content": "x"}])


def test_client_reraises_a_real_outage_untouched(monkeypatch):
    import openai
    monkeypatch.setattr(openai, "APIStatusError", _Status, raising=False)
    with pytest.raises(_Status):
        _client_with(exc=_Status("Internal server error", 500)).complete([{"role": "user", "content": "x"}])


def test_unparseable_tool_arguments_are_also_a_malformed_action():
    """The server returns 200 here — the arguments string the model generated
    just isn't JSON. Same class of failure: the model, not the transport."""
    with pytest.raises(MalformedActionError):
        _client_with(tool_args='{"stage": "open"').complete([{"role": "user", "content": "x"}])


def test_wellformed_arguments_still_parse():
    resp = _client_with(tool_args=json.dumps({"stage": "open"})).complete([{"role": "user", "content": "x"}])
    assert resp.tool_calls[0]["arguments"] == {"stage": "open"}


# ── the meter keeps the episode ───────────────────────────────────────────

def test_a_malformed_action_is_recorded_but_is_not_an_api_error():
    from src.meter.meter import EpisodeMeter
    m = EpisodeMeter("e", "m", "json_mcp", "tool_call", "t1", "hard", 1, 4, "tpl", "pat")
    m.mark_malformed_action(PEG)
    row = m.finalize({"passed": False, "reasons": [], "checks": {"answer": False}})
    assert row["malformed_action"] == 1
    assert row["malformed_action_message"]
    # The two must never be confused: model_api_error is what the circuit
    # breaker counts, and a healthy server must not trip it.
    assert row["model_api_error"] == 0
    assert row["infra_error"] == 0


def test_an_ordinary_episode_reports_no_malformed_action():
    from src.meter.meter import EpisodeMeter
    m = EpisodeMeter("e", "m", "python", "tool_call", "t1", "easy", 1, 2, "tpl", "pat")
    row = m.finalize({"passed": True, "reasons": [], "checks": {"answer": True}})
    assert row["malformed_action"] == 0


def test_the_circuit_breaker_ignores_malformed_actions():
    """main.py counts row['model_api_error'] only. Pinned here because the
    whole point of the reclassification is that a model producing bad syntax
    against a HEALTHY server must not get abandoned mid-run."""
    from src.meter.meter import EpisodeMeter
    m = EpisodeMeter("e", "m", "json_mcp", "tool_call", "t1", "hard", 1, 4, "tpl", "pat")
    m.mark_malformed_action(PEG)
    assert not m.finalize({"passed": False, "reasons": [], "checks": {}})["model_api_error"]


# ── the columns exist ─────────────────────────────────────────────────────

def test_both_columns_are_written_to_the_csv():
    from main import CSV_FIELDS
    from src.meter.meter import EpisodeMeter
    m = EpisodeMeter("e", "m", "python", "tool_call", "t1", "easy", 1, 2, "tpl", "pat")
    row = m.finalize({"passed": True, "reasons": [], "checks": {}})
    assert not set(row) - set(CSV_FIELDS), "meter emits columns the CSV would drop"
    assert "malformed_action" in CSV_FIELDS


def test_loop_scores_the_episode_instead_of_returning_early():
    """The api-error path RETURNS (discarding the episode). The malformed path
    must BREAK, so control falls through to the state-diff + verify below and
    the episode is scored on the state it actually reached."""
    import inspect

    from src.agent import loop
    src = inspect.getsource(loop.run_episode)
    handler = src[src.index("except MalformedActionError"):]
    body = handler[:handler.index("except Exception")]
    # comments stripped: the handler's own comment explains why it does not
    # return, and matching that text would pass the test for the wrong reason
    code = [ln for ln in body.splitlines() if not ln.strip().startswith("#")]
    assert any("break" in ln for ln in code)
    assert not any("return" in ln for ln in code)
