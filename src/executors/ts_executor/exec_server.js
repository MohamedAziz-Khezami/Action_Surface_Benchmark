// exec_server.js — the /exec endpoint running inside the TS executor
// container. Kept fully separate from js_executor/ (its own Dockerfile,
// its own dependency on the `typescript` npm package) since this is the
// only executor that does real, semantic TypeScript type-checking.

'use strict';
const http = require('http');
const vm = require('vm');
const fs = require('fs');
const path = require('path');
const ts = require('typescript');
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

const FILE_NAME = 'code.ts';
const COMPILER_OPTIONS = {
  target: ts.ScriptTarget.ES2020,
  module: ts.ModuleKind.CommonJS,
  skipLibCheck: true,
  strict: false,
};

function formatDiagnostics(diagnostics) {
  return diagnostics
    .map((d) => ts.flattenDiagnosticMessageText(d.messageText, '\n'))
    .join('; ');
}

// `tools` is injected into the vm sandbox at runtime (see execBlock below),
// so a standalone type-check of the submitted code alone would never know
// it exists and would flag every legitimate `tools.find_deals(...)` call as
// "Cannot find name 'tools'". This ambient declaration file gives the
// checker tools.d.ts's real, hand-written signatures instead, so a wrong
// tool argument (wrong name, wrong type, wrong enum value) is caught here,
// statically, not just later as a runtime 422 from the tool-server.
// tools.d.ts is hand-maintained — kept in sync by hand with
// src/tool_server/models.py, not generated from it.
const AMBIENT_FILE_NAME = 'ambient.d.ts';
const AMBIENT_SOURCE = fs.readFileSync(path.join(__dirname, 'tools.d.ts'), 'utf8');

// Type-checks the submitted code in-memory (no real files touched) and, if
// clean, returns the emitted (types-stripped) JS ready to run.
function checkAndTranspileTs(code) {
  const sourceFile = ts.createSourceFile(FILE_NAME, code, COMPILER_OPTIONS.target, true);
  const ambientFile = ts.createSourceFile(
    AMBIENT_FILE_NAME, AMBIENT_SOURCE, COMPILER_OPTIONS.target, true, ts.ScriptKind.TS);
  const host = ts.createCompilerHost(COMPILER_OPTIONS);
  const originalGetSourceFile = host.getSourceFile.bind(host);
  const originalReadFile = host.readFile.bind(host);
  host.getSourceFile = (name, languageVersion, ...rest) => {
    if (name === FILE_NAME) return sourceFile;
    if (name === AMBIENT_FILE_NAME) return ambientFile;
    return originalGetSourceFile(name, languageVersion, ...rest);
  };
  host.readFile = (name) => {
    if (name === FILE_NAME) return code;
    if (name === AMBIENT_FILE_NAME) return AMBIENT_SOURCE;
    return originalReadFile(name);
  };
  host.fileExists = (name) =>
    name === FILE_NAME || name === AMBIENT_FILE_NAME || ts.sys.fileExists(name);

  let outputText = null;
  host.writeFile = (name, text) => {
    if (name.endsWith('.js')) outputText = text;
  };

  const program = ts.createProgram([FILE_NAME, AMBIENT_FILE_NAME], COMPILER_OPTIONS, host);

  const syntactic = program.getSyntacticDiagnostics(sourceFile);
  if (syntactic.length > 0) {
    return { ok: false, code: 'ts_syntax_error', message: formatDiagnostics(syntactic) };
  }

  const semantic = program.getSemanticDiagnostics(sourceFile);
  if (semantic.length > 0) {
    return { ok: false, code: 'ts_type_error', message: formatDiagnostics(semantic) };
  }

  program.emit(sourceFile);
  return { ok: true, js: outputText };
}

// Makes the LAST bare-expression statement an explicit `return`, since an
// async function body doesn't auto-return like a raw vm script does — this
// preserves the "trailing expression = the value" convention exec_server.py
// and js_executor/exec_server.js also implement. Parses as TS (not JS) since
// this now runs on the model's raw TS source, before type-checking — see
// execBlock below for why the wrap has to happen before the check, not after.
function wrapWithReturn(code) {
  const sf = ts.createSourceFile('code.ts', code, ts.ScriptTarget.ES2020, true, ts.ScriptKind.TS);
  if (sf.statements.length === 0) return code;
  const last = sf.statements[sf.statements.length - 1];
  if (ts.isExpressionStatement(last)) {
    return code.slice(0, last.getStart(sf)) + `return (${last.expression.getText(sf)});`;
  }
  return code;
}

async function execBlock(code, maxToolCalls) {
  toolCallCounter.count = 0;
  // undefined => unlimited, so an older harness talking to a newer image
  // behaves exactly as before rather than silently capping at zero.
  toolCallCounter.limit = maxToolCalls ?? null;
  // Wrap BEFORE type-checking, not after: at execution time the code always
  // runs inside `(async () => {...})()`, so `await` is legal there. But
  // type-checking the model's raw code directly (unwrapped) means TS sees a
  // bare top-level `await` outside any function — which TypeScript rejects
  // ("only allowed... when that file is a module") even though the code is
  // completely correct. Checking the same wrapped string that will actually
  // run keeps "what got checked" and "what gets executed" identical.
  const wrappedTs = `(async () => { ${wrapWithReturn(code)} })()`;
  const checked = checkAndTranspileTs(wrappedTs);
  if (!checked.ok) {
    // type-checking happens before any code runs, so no tool call could have
    // occurred yet — tool_calls is always 0 on this path.
    return { ok: false, stdout: '', value: null, tool_calls: 0,
             error: { message: checked.message, code: checked.code, name: null } };
  }

  let stdout = '', value = null, error = null;
  const origLog = console.log;
  console.log = (...a) => { stdout += a.map(String).join(' ') + '\n'; };
  try {
    value = await vm.runInContext(checked.js, sandbox, { timeout: 60000 });
  } catch (e) {
    // "name" is the JS error class (e.g. TypeError, ReferenceError) — TS
    // syntax/type errors are already distinguished above via `code`, so this
    // only ever fires for a genuine runtime mistake or a tool error.
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
        const { code, max_tool_calls: maxToolCalls } = JSON.parse(body);
        const result = await execBlock(code, maxToolCalls);
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
  console.log('ts_executor listening on :8001');
});
