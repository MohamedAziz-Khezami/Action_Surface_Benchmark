# tools_client.py — lives inside the Python executor container.
from __future__ import annotations

import requests


class ToolCallLimitExceeded(RuntimeError):
    """Raised when a single execute() block exceeds its tool-call budget.

    Its own class, not a bare RuntimeError, so the meter can bucket a cap hit
    separately from a genuine bug in the model's code. Conflating the two would
    make the batching ablation look like it degraded code quality when all it
    did was enforce the cap it was asked to enforce."""


#this is basically the python sdk that runs the requests to the backend server from tool.get_contact() etc...
class Tools:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.call_count = 0  # reset per /exec call by exec_server.py; feeds the meter's tool_calls_made
        # Max tool calls allowed in ONE /exec block; None = unlimited (default).
        # Set per request by exec_server.py, never baked into the image, so the
        # same container can serve capped and uncapped episodes and the ablation
        # needs no rebuild.
        self.call_limit: int | None = None

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)

        def call(**kwargs):
            # Checked BEFORE the request, so a rejected call never reaches the
            # tool-server: a cap that let the write through and only complained
            # afterwards would not restrict the agent's behaviour at all.
            if self.call_limit is not None and self.call_count >= self.call_limit:
                exc = ToolCallLimitExceeded(
                    f"tool_call_limit_exceeded: this execute() block may make at most "
                    f"{self.call_limit} tool call(s); '{name}' would be number "
                    f"{self.call_count + 1}. Return what you have and make the "
                    f"remaining calls in a following execute() block.")
                exc.code = "tool_call_limit_exceeded"
                raise exc
            self.call_count += 1
            resp = requests.post(f"{self.base_url}/{name}", json=kwargs, timeout=30)
            result = resp.json()  # every response is HTTP 200; success/failure is signaled by result["success"]
            if not result["success"]:
                err = result["error"]
                exc = RuntimeError(f"{err['code']}: {err.get('technical_message')}")
                exc.code = err["code"]  # was previously lost, only baked into the message text
                raise exc
            return result["data"]
        return call
