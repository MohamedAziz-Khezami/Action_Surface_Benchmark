// exec_server.js — the /exec endpoint running inside the JS executor container.
'use strict';
const http = require('http');
const vm = require('vm');
const acorn = require('acorn');
const { makeToolsProxy } = require('./tools_client');

// Model code routinely leaves a promise unhandled — e.g. calling an async tool
// without `await`, which then rejects when the arguments are invalid. Node's
// default is to crash the process on an unhandled rejection (and on an uncaught
// exception), which would kill this server and make every later request in the
// container fail with "connection refused" — turning a recoverable model
// mistake into an episode-ending infra error that the analysis excludes. Absorb
// them so one bad code block is contained as a normal failed exec instead.
process.on('unhandledRejection', (reason) => {
  console.error('[executor] ignored unhandledRejection:', reason && reason.message ? reason.message : reason);
});
process.on('uncaughtException', (err) => {
  console.error('[executor] ignored uncaughtException:', err && err.message ? err.message : err);
});

const TOOL_SERVER_URL = process.env.TOOL_SERVER_URL || 'http://localhost:8000';
const { proxy: tools, counter: toolCallCounter } = makeToolsProxy(TOOL_SERVER_URL);
const sandbox = vm.createContext({ tools, console, JSON, Math, Date });

function wrapWithReturn(code) {
  let ast;
  try {
    ast = acorn.parse(code, { ecmaVersion: 2020, sourceType: 'script' });
  } catch {
    return code; // let vm.runInContext surface the real syntax error
  }
  if (ast.body.length === 0) return code;
  const last = ast.body[ast.body.length - 1];
  if (last.type === 'ExpressionStatement') {
    return code.slice(0, last.start) + `return (${code.slice(last.expression.start, last.expression.end)});`;
  }
  return code;
}

async function execBlock(code) {
  let stdout = '', value = null, error = null;
  toolCallCounter.count = 0;
  const origLog = console.log;
  console.log = (...a) => { stdout += a.map(String).join(' ') + '\n'; };
  try {
    const wrapped = `(async () => { ${wrapWithReturn(code)} })()`;
    value = await vm.runInContext(wrapped, sandbox, { timeout: 60000 });
  } catch (e) {
    // "name" is the JS error class (e.g. SyntaxError, TypeError, ReferenceError)
    // so the meter can distinguish a syntax error from a tool error from any
    // other runtime mistake, none of which set a meaningful "code" on their own.
    error = { message: e.message, code: e.code || null, name: e.name || null };
  } finally {
    console.log = origLog;
  }

  let safeValue = null;
  try {
    safeValue = value === undefined ? null : JSON.parse(JSON.stringify(value));
  } catch {
    safeValue = String(value);
  }
  return { ok: !error, stdout, value: safeValue, error, tool_calls: toolCallCounter.count };
}

const server = http.createServer((req, res) => {
  if (req.method === 'GET' && req.url === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ ok: true }));
    return;
  }
  if (req.method === 'POST' && req.url === '/exec') {
    let body = '';
    req.on('data', (chunk) => { body += chunk; });
    req.on('end', async () => {
      try {
        const { code } = JSON.parse(body);
        const result = await execBlock(code);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(result));
      } catch (e) {
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: false, stdout: '', value: null,
                                  error: { message: e.message, code: 'server_error' } }));
      }
    });
    return;
  }
  res.writeHead(404);
  res.end();
});

server.listen(8001, '0.0.0.0', () => {
  console.log('js_executor listening on :8001');
});
