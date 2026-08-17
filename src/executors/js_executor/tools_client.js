// tools_client.js — lives inside the JS executor container. `tools` is
// what generated code sees. Genuinely asynchronous — fetch() is inherently
// Promise-based in Node, so tool calls require a real `await`. Every call
// is a real HTTP request to the tool-server, reached only over the private
// per-episode Docker network (this container has no direct database access).
'use strict';

// `counter` is a mutable {count, limit} object exec_server.js resets before
// each /exec call and reads afterward, feeding the meter's tool_calls_made.
// `limit` is the max tool calls allowed in ONE /exec block (null = unlimited,
// the default). It is set per request rather than baked into the image, so the
// same container serves capped and uncapped episodes with no rebuild.
function makeToolsProxy(baseUrl) {
  const counter = { count: 0, limit: null };
  const proxy = new Proxy({}, {
    get(_target, prop) {
      if (typeof prop !== 'string') return undefined;
      return async (args) => {
        // Checked BEFORE the request, so a rejected call never reaches the
        // tool-server: a cap that let the write through and only complained
        // afterwards would not restrict the agent's behaviour at all.
        if (counter.limit !== null && counter.count >= counter.limit) {
          const err = new Error(
            `tool_call_limit_exceeded: this execute() block may make at most ` +
            `${counter.limit} tool call(s); '${prop}' would be number ` +
            `${counter.count + 1}. Return what you have and make the remaining ` +
            `calls in a following execute() block.`);
          err.code = 'tool_call_limit_exceeded';
          // Own name, not a bare Error, so the meter can bucket a cap hit
          // separately from a genuine bug in the model's code.
          err.name = 'ToolCallLimitExceeded';
          throw err;
        }
        counter.count += 1;
        const resp = await fetch(`${baseUrl}/${prop}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(args || {}),
        });
        const result = await resp.json(); // every response is HTTP 200; success/failure is signaled by result.success
        if (!result.success) {
          const err = new Error(`${result.error.code}: ${result.error.technical_message ?? ''}`);
          err.code = result.error.code;
          throw err;
        }
        return result.data;
      };
    },
  });
  return { proxy, counter };
}

module.exports = { makeToolsProxy };
