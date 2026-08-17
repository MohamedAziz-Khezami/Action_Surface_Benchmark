
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import openai

from config import MODEL_REQUEST_TIMEOUT_S
from src.llm_clients.registry import ModelConfig




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
        resp = self._client.chat.completions.create(**kwargs)
        message = resp.choices[0].message

        tool_calls = []
        for tc in (message.tool_calls or []):
            tool_calls.append({"id": tc.id, "name": tc.function.name,
                                "arguments": json.loads(tc.function.arguments)})

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
