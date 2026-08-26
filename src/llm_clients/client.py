
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import openai

from config import MODEL_REQUEST_TIMEOUT_S
from src.llm_clients.registry import ModelConfig




class MalformedActionError(RuntimeError):
    """The model emitted output that could not be turned into a usable action.

    Deliberately NOT a model_api_error. A transport failure means the server
    stopped serving and every further episode buys another timeout, which is
    what main.py's circuit breaker exists to stop. This is the opposite: the
    server is healthy and answered promptly — the MODEL produced tool-call
    syntax the server could not parse, or arguments that are not valid JSON.

    That is a failure at the task, and it must stay in the denominator.
    Discarding it would delete a real, surface-dependent failure mode from
    the results: json_mcp emits one structured call per action, 2-12 per
    episode, across 17 tools with different argument shapes, while a code
    surface emits 1-3 execute() wrappers of one fixed two-field shape. So
    json_mcp is far more exposed to this, and excluding these episodes would
    quietly compute its pass rate only over the episodes where it happened to
    stay grammatical."""


# Substrings that identify a 5xx as "the server could not parse the MODEL's
# output" rather than "the server is broken". Matched case-insensitively and
# only on a 5xx, so a genuine outage is never swallowed as a model failure.
_MALFORMED_OUTPUT_MARKERS = (
    "does not match the expected",   # llama.cpp: "...expected peg-native format"
    "peg-native",
    "failed to parse",
)


def _is_malformed_output(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status is None or status < 500:
        return False
    text = str(exc).lower()
    return any(marker in text for marker in _MALFORMED_OUTPUT_MARKERS)


@dataclass
class ModelResponse:
    content: str
    tool_calls: list[dict] = field(default_factory=list)  # [{"id", "name", "arguments": dict}]
    input_tokens: int = 0
    output_tokens: int = 0


class OpenAICompatibleClient:
    """Covers OpenAI, Ollama, vLLM, and llama.cpp — all speak the same
    /v1/chat/completions protocol; only base_url/api_key differ."""

    def __init__(self, config: ModelConfig):
        api_key = os.environ.get(config.api_key_env, "not-needed") if config.api_key_env else "not-needed"
        # An explicit timeout matters: the SDK's 600s default lets one stuck
        # turn stall an episode for ten minutes (see MODEL_REQUEST_TIMEOUT_S).
        self._client = openai.OpenAI(base_url=config.base_url, api_key=api_key,
                                      timeout=MODEL_REQUEST_TIMEOUT_S)
        self._model_id = config.model_id

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> ModelResponse:
        kwargs = {"model": self._model_id, "messages": messages}
        if tools:
            kwargs["tools"] = tools
        try:
            resp = self._client.chat.completions.create(**kwargs)
        except openai.APIStatusError as e:
            if _is_malformed_output(e):
                raise MalformedActionError(str(e)) from e
            raise
        message = resp.choices[0].message

        tool_calls = []
        for tc in (message.tool_calls or []):
            # Arguments arrive as a JSON *string* the model generated. When it
            # is malformed the server still returns 200, so this is the same
            # class of failure as the 5xx above — the model, not the transport.
            try:
                arguments = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError) as e:
                raise MalformedActionError(
                    f"tool call {tc.function.name!r} had unparseable arguments: {e}") from e
            tool_calls.append({"id": tc.id, "name": tc.function.name,
                                "arguments": arguments})

        return ModelResponse(
            content=message.content or "",
            tool_calls=tool_calls,
            input_tokens=resp.usage.prompt_tokens,
            output_tokens=resp.usage.completion_tokens,
        )

#Not used in this benchmark
# class AnthropicClient:
#     """Claude's native API — different message/tool-calling shape from
#     OpenAI, so this normalizes both directions: pulls a leading {"role":
#     "system", ...} message out of `messages` (Anthropic wants it as a
#     top-level `system` param, not in the messages list), and converts
#     OpenAI-shaped tool schemas ({"type": "function", "function": {...}})
#     into Anthropic's ({"name", "description", "input_schema"})."""
#
#     def __init__(self, config: ModelConfig):
#         api_key = os.environ.get(config.api_key_env) if config.api_key_env else None
#         self._client = anthropic.Anthropic(api_key=api_key)
#         self._model_id = config.model_id
#
#     def complete(self, messages: list[dict], tools: list[dict] | None = None) -> ModelResponse:
#         messages = list(messages)
#         system = None
#         if messages and messages[0]["role"] == "system":
#             system = messages.pop(0)["content"]
#
#         kwargs = {"model": self._model_id, "max_tokens": _ANTHROPIC_DEFAULT_MAX_TOKENS,
#                   "messages": messages}
#         if system:
#             kwargs["system"] = system
#         if tools:
#             kwargs["tools"] = [
#                 {"name": t["function"]["name"], "description": t["function"].get("description", ""),
#                  "input_schema": t["function"]["parameters"]}
#                 for t in tools
#             ]
#
#         resp = self._client.messages.create(**kwargs)
#
#         content_text = ""
#         tool_calls = []
#         for block in resp.content:
#             if block.type == "text":
#                 content_text += block.text
#             elif block.type == "tool_use":
#                 tool_calls.append({"id": block.id, "name": block.name, "arguments": block.input})
#
#         return ModelResponse(
#             content=content_text,
#             tool_calls=tool_calls,
#             input_tokens=resp.usage.input_tokens,
#             output_tokens=resp.usage.output_tokens,
#         )


_CLIENTS = {"openai_compatible": OpenAICompatibleClient}


def make_client(config: ModelConfig):
    return _CLIENTS[config.backend](config)
