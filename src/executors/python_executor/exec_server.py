# exec_server.py
from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import signal

from flask import Flask, jsonify, request

from tools_client import Tools

app = Flask(__name__)
tools = Tools(os.environ.get("TOOL_SERVER_URL", "http://localhost:8000"))


_EXEC_TIMEOUT_S = 60


class ExecTimeout(Exception):
    pass


def _raise_timeout(signum, frame):
    raise ExecTimeout(f"execution exceeded {_EXEC_TIMEOUT_S}s")


signal.signal(signal.SIGALRM, _raise_timeout)


def run_capturing_last_expr(code: str, namespace: dict):
    tree = ast.parse(code, mode="exec")
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        last = tree.body.pop()
        exec(compile(tree, "<agent_code>", "exec"), namespace)
        return eval(compile(ast.Expression(last.value), "<agent_code>", "eval"), namespace)
    exec(compile(tree, "<agent_code>", "exec"), namespace)
    return None


@app.route("/exec", methods=["POST"])
def exec_code():
    payload = request.get_json()
    code = payload["code"]
    stdout_buf = io.StringIO()
    value, error = None, None
    tools.call_count = 0
    # Absent key => unlimited, so an older harness talking to a newer image
    # behaves exactly as before rather than silently capping at zero.
    tools.call_limit = payload.get("max_tool_calls")
    try:
        signal.alarm(_EXEC_TIMEOUT_S)
        try:
            with contextlib.redirect_stdout(stdout_buf):
                value = run_capturing_last_expr(code, {"tools": tools})
        finally:
            signal.alarm(0)
        json.dumps(value)  # confirm JSON-safe before returning
    except TypeError:
        value = str(value)
    except Exception as e:  # model code can raise anything; always report, never crash the server
        # "name" is the exception class (e.g. SyntaxError, NameError, RuntimeError,
        # ExecTimeout) so the meter can tell a syntax error apart from a tool error
        # apart from any other runtime mistake, none of which set a meaningful
        # "code" on their own.
        error = {"message": str(e), "code": getattr(e, "code", None), "name": type(e).__name__}
    return jsonify({"ok": error is None, "stdout": stdout_buf.getvalue(),
                     "value": value, "error": error, "tool_calls": tools.call_count})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001)
