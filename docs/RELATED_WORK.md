# Related Work — how Ent-Agent-Bench differs

Full-text reading of the primary papers (not abstracts), plus a sweep of the
adjacent field. Written to answer one question: **is this benchmark already
built, and if not, what exactly is the gap?**

Date: 2026-07-23

---

## 0. The headline

**The gap is real, but it is not where the README currently claims it is.**

Every benchmark below — all of them — **fixes the action interface and varies
the model.** τ-bench fixes function-calling. CRMArena-Pro fixes SOQL/SOSL.
WorkBench fixes ReAct text tool calls. WorkArena fixes browser actions.
AppWorld fixes Python code. Agent-Diff fixes Bash code.

Ent-Agent-Bench is the only one that **fixes the model, the task, the data, the
world, the tool implementations and the grader, and varies the action
interface.** That is a genuinely different experimental axis. It makes your
project an **ablation study over the agent's action surface**, not a rival
enterprise capability benchmark.

Which means:

- ❌ You are **not** competing with CRMArena-Pro. Stop positioning against it —
  you will lose (Salesforce has 25 objects, real sandboxed orgs, 4,280 queries),
  and it isn't your question anyway.
- ✅ You **are** doing something none of them do. But two papers have taken
  chunks of the ground you thought was empty, and you need to know about them.

### The two papers that should worry you

1. **CodeAct** (ICML'24) already established *code beats JSON* — up to +20%
   success, ~30% fewer turns, across 17 LLMs. **Your headline finding is
   already published.** You cannot lead with "code-mode wins."
2. **Agent-Diff** (arXiv 2602.11224, v3 Apr 2026) — code execution + enterprise
   APIs + **state-diff verification** + cost/token/`Score-per-$` reporting +
   Bayesian credible intervals. This is your architecture, shipped four months
   ago, minus the comparison. See §7 — read it before you write another line.

Your remaining, defensible novelty is in §9. It's narrower than you thought but
it's real, and it's more interesting than "code-mode wins."

---

## 1. τ-bench (Sierra, NeurIPS'24) — arXiv 2406.12045

**Read in full.** This is the paper your design most resembles, and the one you
should be borrowing from most aggressively.

| | τ-bench | Ent-Agent-Bench |
|---|---|---|
| Question | Can agents follow domain policy while talking to a user? | Does the action surface change outcomes? |
| Domains | τ-retail, τ-airline | crm_scenario |
| Data | 500 users / 50 products / 1,000 orders; 500 users / 300 flights / 2,000 reservations | ~60 contacts / 40 leads / 35 deals per world |
| Tools | 15 (7 write / 8 read) retail; 13 airline | 17 |
| Tasks | 115 + 50 = **165**, hand-annotated | ~120 generated from 15 templates |
| Action interface | **Function calling only** (+ ReAct/Act text ablation) | 4 surfaces × 2 modes |
| Verification | Final DB state == unique annotated goal DB, **plus** substring check on agent's messages | 6 checks: answer + added/changed/counts + forbidden |
| Reliability | **pass^k** over ≥3 trials | single trial ❌ |
| Cost | **Reported** — $0.38/task agent + $0.23 user | ❌ |

### The four things to steal

**1. The pass^k estimator.** They give the unbiased form directly — for `n`
trials with `c` successes:

```
pass^k = E_task[ C(c,k) / C(n,k) ]        pass@k = 1 − E_task[ C(n−c,k) / C(n,k) ]
```

Use this exact estimator, not a naive `p^k`. Their result: gpt-4o at 61.2%
pass^1 on retail collapses to **<25% at pass^8**.

**2. Their cost finding is the strongest existing evidence for your
catalog-scaling experiment — and you should quote it.**

> For the agent, the input prompt / completion output take up **95.9% / 4.1%**
> of the price respectively, so the cost is mainly due to long system prompt
> (domain policy + function definitions).

At **15 tools**, 96% of agent cost is already the input prompt carrying tool
schemas. That is the mechanism code-mode attacks, measured independently by a
benchmark that wasn't even trying to study it. Your `--catalog-size` sweep is
the direct experimental follow-up to this sentence. Put it in your intro.

**3. `policy.md` as a first-class artifact.** Their agent gets a Markdown policy
document as system prompt, and crucially **some rules are enforced by the API
and some are not** — the agent must self-enforce the rest. Your CRM has no
policy layer at all; every constraint is enforced by the tool server. Adding an
unenforced-policy layer is cheap and would let you ask a question nobody has
asked: **does code-mode follow written policy worse than JSON-MCP?** Plausible
mechanism — a batched loop applies a policy judgment once and fans it out over
50 rows, where per-call mode re-decides each time. If true, that is a genuinely
novel and enterprise-critical finding.

**4. "Trade quantity for quality."** Explicit design principle: 165 tasks run
many times beats thousands run once. Your ~120 tasks × 1 trial should become
~120 tasks × 5+ trials. Same compute, vastly more information.

### Where you are genuinely better

- Their tasks are **hand-annotated** — Stage III is manual iteration until no
  ambiguity remains, ">40 gpt-4-turbo trials" per retail task to validate. Your
  constructive generator + `audit.py` + `cheater.py` gets the same guarantee
  **programmatically and reproducibly**. That is a real methodological
  contribution and it is defensible in review.
- Their `routput` check is **substring matching** on agent messages. The 2026
  validity audit (§8) flags exactly this as a failure mode. Your typed,
  field-wise `answer` check is stronger.

### Their stated limitations you should not inherit
User-simulator typos/ambiguity; simulator LM reasoning limits; **40% user
simulator error rate in τ-retail** (measured later in τ²). You avoid all of this
by having no user simulator — a real advantage for reproducibility, and a real
limitation for realism. Say both.

---

## 2. τ²-bench (Sierra, 2025) — arXiv 2506.07982

Dual-control: **both agent and user have tools** over a shared Dec-POMDP state,
so the agent must *guide the user* through actions it cannot perform itself.
Telecom domain. pass^1: gpt-4.1 34%, o4-mini 42%, claude-3.7-sonnet 49%.

Three things relevant to you:

1. **The compositional task generator.** Tasks are composed programmatically
   from atomic base scenarios, each defined by `(initialization, solution,
   assertion)` functions — giving "provable correctness of tasks, complete
   domain coverage, explicit control over complexity... removes the manual
   effort and potential brittleness associated with hand-crafted task suites."
   **This is your `template_interpreter.py` + `world_builder.py`, arrived at
   independently by Sierra.** Strong validation of your design — cite it as
   convergent evidence rather than treating your generator as novel.
2. **Categorized evaluation criteria** — DB check, status assertions, natural
   language assertions, communication info check, action matching. Your six
   checks are a subset. Worth adopting their vocabulary for comparability.
3. **They measure their own simulator's error rate** (16% telecom vs 40%
   retail). Measuring your harness's own error rate is a credibility move you
   can copy cheaply — you already have `infra_error` / `episode_error` /
   `model_api_error` flags and never report them as a harness-quality number.

**Domain packaging** — this is your §6 extensibility answer, prebuilt:
`data/tau2/domains/<name>/` containing `tasks.json`, `policy.md`, `db.json`,
`user_db.json`, `split_tasks.json`, plus `tests/test_domains/test_<name>/`.
Copy this layout deliberately.

---

## 3. CRMArena & CRMArena-Pro (Salesforce, 2024/2025)

Your lab mates were right that it looks similar. It isn't — it's orthogonal.

**CRMArena** (2411.02305): 16 interconnected industrial objects, latent
variables simulating realistic distributions (complaint habits, policy
violations), 9 tasks across 3 personas (service agent / analyst / manager). SOTA
agents: <40% with ReAct, <55% with function calling.

**CRMArena-Pro** (2505.18878):

- **Environment:** real **Salesforce sandbox orgs**, 25 interconnected objects.
  B2B org = 29,101 records; B2C = 54,569 records.
- **Action interface:** **SOQL / SOSL queries** — Salesforce's own query
  languages — with `Execute` / `Respond` actions. *Not* function calling, *not*
  code, *not* MCP.
- **Tasks:** 19 tasks × 100 instances × 2 orgs = 3,800, plus 480 confidentiality
  queries = **4,280 total**.
- **Four skills:** Database Querying & Numerical Computation (8 tasks), Info
  Retrieval & Textual Reasoning (5), Policy Compliance (4), Workflow Execution (2).
- **Verification:** exact match / F1 (token overlap) for generative answers /
  **gpt-4o as LLM judge** for confidentiality.
- **Results:** best single-turn gemini-2.5-pro 58.3% B2C, 54.1% B2B; multi-turn
  drops to **~35%**. Confidentiality awareness is **near-zero (0–2.1%)** without
  prompting, ~24% with it — "often at a cost to task performance."
- **Cost:** Figure 5 plots avg cost per query vs performance. **They already do
  the cost-vs-accuracy frontier plot.** No latency, no tokens.

### How you differ — three hard boundaries

1. **Read-heavy vs write-heavy.** 13 of their 19 tasks are querying/retrieval/
   reasoning. Yours are *mutations* graded by DB diff. Different capability.
2. **Their action interface is a query language, not a tool protocol.** SOQL is
   neither MCP-style structured calling nor general code. Your comparison
   doesn't even apply to their setup.
3. **They use an LLM judge and F1.** You are fully deterministic. Given the 2026
   validity audit's finding of **18.9-point score spread across 23 identical
   LLM-judge runs** (§8), determinism is a defensible advantage — lead with it.

### What to steal
The **confidentiality-awareness axis**. They found agents will happily leak
sensitive data unless explicitly prompted, and that prompting for it *costs task
performance*. That's a tradeoff curve, and it's exactly the shape of your
blast-radius argument. An "unauthorized read/write under code-mode vs JSON-MCP"
result would sit naturally next to it.

---

## 4. WorkBench (2405.00823)

Closest to yours in *spirit* — sandboxed DBs, outcome-based grading, side-effect
analysis.

- **5 databases:** Calendar (300 events), Email (500), Analytics (500 visits),
  CRM (200 customers), Project Management (300 tasks). **26 tools.**
- **Task generation:** **69 hand-written templates × 10 entity-substituted
  variations = 690 tasks** (480 single-domain, 210 multi-domain), 3 linguistic
  phrasings per template, 0–12 actions per task, 18% requiring no action.
- **Evaluation:** "outcome-centric" — unique unambiguous ground-truth DB state;
  any action sequence reaching it counts, so agents can recover from
  intermediate errors. **Identical philosophy to your verifier.**
- **Results:** GPT-4 43% (all tools) / 49% (required tools only); Claude-2 26%;
  Mixtral 16%; GPT-3.5 0%; Llama2-70B 0%. By domain (GPT-4): Calendar 65%,
  Email 48%, Analytics 39%, PM 39%, CRM 23%.
- **Side effects:** **29% of multi-domain failures involved side effects**;
  Analytics domain hit a **54% side-effect rate**. Example: cancelling meeting
  `00000196` instead of `00000035`.

### The two most useful facts here

1. **Their template→variation ratio is 69×10. Yours is 15×~8.** You are
   ~4.5× under-templated. Template *diversity* is your corpus's real bottleneck,
   not instance count — 30 instances of the same 15 templates is 15 tasks with
   error bars, not 120 tasks.
2. **Side-effect analysis is a published precedent for your blast-radius
   metric.** You do not have to invent or justify it — cite WorkBench, then note
   that nobody has measured whether side-effect rate *depends on the action
   interface*. That's your contribution, and their 29%/54% numbers make it
   obviously worth asking.

Their stated limitation is one you share: the sandbox underrepresents real
complexity (real inboxes have tens of thousands of legacy emails, spam,
malformed data). Worth pre-empting in your own limitations section.

---

## 5. WorkArena / WorkArena++ / BrowserGym (ServiceNow, 2403.07718)

Least similar — different modality entirely. Included because your lab mates
will ask.

- **29 tasks / 18,050 instances** on a live ServiceNow instance: Lists (12
  tasks, 6,900 inst.), Forms (5, 5,000), Service catalogs (9, 3,550), Menus (2,
  1,600), Knowledge bases (1, 1,000).
- **Action space is a browser** (BrowserGym): `click(bid)`, `fill(bid,text)`,
  `select_option`, coordinate mouse/keyboard, `goto`, `send_msg_to_user`, and
  **unrestricted Playwright Python**. Observations: DOM snapshot, AXTree,
  screenshot, error messages.
- **Validation:** query the DB for entries the agent created and check values.
  Every task ships a **"cheating function"** (Playwright script) that proves the
  task is solvable and provides ground truth.
- **Results:** GPT-4 **54.8%**, GPT-3.5 18.6%, CodeLLAMA 0%.
- **Limitation that dominates the paper:** pages are **40k–500k tokens** of DOM.

**Relevance to you:** their "cheating function" ≙ your golden solution, and
their DB-query validation ≙ your state diff — convergent design, worth a
one-line cite. Their real lesson is the opposite of yours: at the browser layer
the *observation* is the bottleneck; at the tool layer the *action encoding* is.
Those are the two halves of the same context-economy story, and framing it that
way makes your paper look situated rather than narrow.

---

## 6. AppWorld (ACL'24 Best Resource Paper, 2407.18901)

**The single most important precedent for code-as-action, and it is not in your
README.**

- Controllable simulation of **9 apps**, **457 APIs** (~50/app, 1,470
  arguments), **750 tasks**.
- **The agent writes and executes Python that calls the app APIs.** Code-as-
  action, by construction.
- **Evaluation:** state-based unit tests taking DB snapshots **before and after**,
  checking that **all expected and no unexpected** database changes occurred.

That last sentence is your `expected_added` + `expected_changed` +
`exact_*_count` + `forbidden` checks, published in 2024. **Your verifier is not
novel.** Cite AppWorld as the origin of the design, and make your contribution
the *comparison across surfaces*, not the verification scheme.

**The important asymmetry:** AppWorld is 457 APIs. You are 17. AppWorld
exists at the scale where code-mode's context argument bites; your corpus does
not. Reviewers who know AppWorld will ask why. `--catalog-size` is your answer.

---

## 7. ⚠️ Agent-Diff (arXiv 2602.11224 v3, Apr 2026) — read this today

**The nearest neighbor to your work by a wide margin.** Independent, four months
old, and it took a real slice of the ground you're standing on.

- **Domain:** 4 enterprise SaaS APIs — Box, Google Calendar, Linear, Slack —
  **108 unique endpoints**, **224 tasks**, **9 frontier models**.
- **Environment:** containerized **replicas** of the real APIs, exposing the same
  endpoints and error schemas; all network traffic intercepted and routed
  locally. *Same trust-boundary trick as your executor/tool-server split.*
- **Action interface:** agent emits **Bash code blocks** (curl/jq/grep/sed) run
  in a sandboxed container. Code-execution only.
- **Evaluation:** "**state-diff contract**" — before/after snapshots yielding a
  deterministic JSON diff of every insert/update/delete, checked against
  expected changes via assertions. Plus a `clean(τ)` gate so an unclean
  trajectory scores zero regardless of partial progress.
- **Metrics:** Pass rate, assertion-weighted Score, **Cost ($)**, **Tokens**,
  **Score/$**, and **95% Bayesian credible intervals**.
- **Results (no-docs):** deepseek-v3.2 88.1±2.4 (76% pass, $0.03), devstral-2512
  86.0, qwen3-vl-235b 79.2, grok-4.1-fast 74.9 (**best Score/$ at 7,489**),
  claude-haiku-4.5 49.3 ($0.22), llama-4-scout 38.0.
- **Ablation:** three documentation conditions — **no-docs (~400 tok) /
  relevant-docs (~3.2–10k) / all-docs (~22.3k)** — explicitly testing "whether
  irrelevant documentation degrades performance via context dilution."

### What this costs you

| Thing you thought was yours | Status |
|---|---|
| State-diff verification on enterprise APIs | ❌ Published (also AppWorld 2024) |
| Sandboxed code execution against replica APIs | ❌ Published |
| Cost + tokens + cost-efficiency metric | ❌ Published (`Score/$`) |
| Confidence intervals on agent benchmarks | ❌ Published (Bayesian CrI) |
| Context-budget ablation | ⚠️ Partially — they vary *docs*, you'd vary *catalog size* |

### What it does **not** do — and this is the whole game

Their own Table 1 positions benchmarks along an **"interaction model" axis:
structured tool calling via MCP/JSON schemas vs direct API access vs
agent-written code.** They name the axis explicitly. Then they **pick one point
on it** (agent-written Bash) and vary the model, like everyone else.

**Nobody has run the comparison along that axis under controlled conditions.**
Agent-Diff drew the map and left the experiment undone. That is your paper —
and you can now cite their own framing to motivate it, which is a far stronger
opening than anything in your current README.

**Action:** read the full PDF, and reuse their Table 1 design-space taxonomy as
your related-work structure. Placing Ent-Agent-Bench as *the row that varies
interaction model with everything else held constant* makes your contribution
legible in one glance.

---

## 8. The rest of the field, briefly

**Tool-calling / function-calling benchmarks** — all fix the interface at
structured JSON calls:

- **BFCL v3/v4** (Berkeley) — multi-turn/multi-step function calling; 200 base
  trajectories + 800 with added complexity. The de facto function-calling leaderboard.
- **ToolSandbox** (Apple, 2408.04682) — stateful tool execution, implicit state
  dependencies between tools, built-in user simulator, milestone-based
  trajectory evaluation. The closest to yours on *statefulness*.
- **API-Bank** — the benchmark CodeAct re-purposed for its JSON-vs-code
  comparison. Atomic single calls; no state verification.
- **NESTFUL** (nested call sequences), **ComplexFuncBench**, **CRITICTOOL**
  (self-correction after tool errors), **ToolEmu** (LM-emulated tools for safety
  risk), **MetaTool**, **ToolBench**.

**MCP-specific** — a crowded 2025–26 cluster, all measuring models against MCP
servers, none comparing MCP *against* an alternative interface:

- **MCP-Universe** (231 tasks, 11 servers, 6 domains; GPT-5-High 44.2%, Grok-4
  33.3%; notably Cursor and Claude Code beat neither ReAct)
- **MCP-Bench** (Accenture — 28 live servers, 250 tools, LLM judge)
- **MCPBench** (ModelScope — accuracy, **latency and token consumption** under
  fixed LLM/agent config; closest existing thing to your enterprise metrics)
- **MCP-AgentBench**, **MCPToolBench++**, **MCP-RADAR**, **MCPWorld**
  (GUI/API + outcome eval), **LiveMCPBench**, **MCP-Atlas**

**Enterprise/workplace suites:**

- **TheAgentCompany** — self-contained simulated company: GitLab, OwnCloud,
  Plane, RocketChat, LLM-backed simulated colleagues. SWE/HR/Admin/PM/Research/
  Finance. The most *environmentally* realistic option.
- **ITBench** (IBM) — 102 scenarios in SRE / CISO / FinOps, "easily extended by
  community contributions." Agents resolve **11.4% SRE / 25.2% CISO / 25.8%
  FinOps**. ITBench-AA (May 2026, with Artificial Analysis): all frontier models
  <50% on 59 SRE tasks; Claude Opus 4.7 leads at 47%. **Study their extension
  story — community-contributed scenarios is exactly your §6 goal.**
- **OfficeBench** — cross-application office automation.
- **EnterpriseClawBench** (2606.23654) — **852 reproducible tasks recovered from
  real proprietary workplace agent sessions**, with fixtures, role classes, hard
  rules and semantic rubrics. This is the "real cases" your lab mates asked for,
  done by people with access to real sessions. Worth reading precisely because
  it shows what "real" costs and why archetypes are the right call for you.
- **GBA-Bench** (Automation Anywhere, proprietary) — 7 business domains.
- **UI-CUBE** — enterprise computer-use, explicitly "beyond task accuracy to
  operational reliability."

**Methodology / validity — read these, they protect you:**

- **"How We Broke Top AI Agent Benchmarks"** (2605.12673) — all 8 of SWE-bench,
  WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench scored
  near-perfectly without solving anything. Your `cheater.py` is the defense.
- **Agentic Benchmark Checklist** (2507.02825) — "SWE-bench Verified uses
  insufficient test cases, while TAU-bench counts empty responses as
  successful"; performance mis-estimated by up to 100% relative. Applying ABC to
  CVE-Bench cut overestimation 33%.
- **"Benchmarking the Benchmarks: A Validity Audit of Tool-Calling Evaluation"**
  (2607.02577) — audited BFCL v4, τ²-Bench Retail, LiveMCPBench, MCP-Atlas over
  496 expert-validated tasks. **18.5% evaluator–human misalignment** (9.8%
  τ²-Bench → 30.5% LiveMCPBench). LLM-judge instability: LiveMCPBench scored
  **57.9%–76.8% across 23 identical runs**.
  **⚠️ The deterministic-evaluator failures they name are yours too:** *brittle
  state matching that rejects valid alternative outcomes*, *trajectory lock-in
  preventing credit for corrective actions*, *exact-match constraints that
  over-specify solutions*. Your `exact_added_count` / `exact_changed_count` /
  `forbidden` checks are precisely this shape. **Audit a sample of your failed
  episodes by hand and report your own evaluator–human agreement rate.** If it's
  ≥95% you have a defensible claim nobody else in this space is making; if it
  isn't, better you find out than a reviewer.
- **"Log analysis is necessary for credible evaluation"** (2605.08545) — tool-use
  errors >50% of failures; scaffold changes swing SWE-bench by 20 points.
- **"Notation Matters"** (2605.29676) — token-optimized schema formats (TOON,
  TRON) across BFCL / MCPToolBench++ / MCP-Universe / StableToolBench: TRON −27%
  tokens at up to −14pp accuracy; TOON −18% at −9pp. **Directly adjacent to your
  thesis and a natural fifth surface** — it shows the token/accuracy tradeoff is
  real and measurable, and that cheaper encodings usually cost accuracy. Your
  question becomes: does code-mode escape that tradeoff or obey it?

---

## 9. So what is actually yours

After all of the above, five things survive. Only five — but they cohere.

1. **The controlled action-interface comparison.** Same task, same world, same
   tools, same grader, same turn budget, same trust boundary — only the action
   encoding varies. CodeAct compared JSON/text/code, but on **API-Bank's atomic
   single calls**, with no state-diff verification, no sandbox parity, no cost
   accounting. **Nobody has done this on stateful, mutating, DB-verified enterprise
   tasks.** This is the paper.
2. **Sandbox parity as an explicit experimental control.** Your executor has
   zero filesystem access to the DB and must go over HTTP to the same tool-server
   `json_mcp` uses. Without this, any code-vs-tools result is confounded. State
   it as a *methodological requirement for this class of comparison* — that
   framing makes it a contribution rather than an implementation detail.
3. **A typed surface.** TypeScript with real `ts.createProgram` semantic
   checking against hand-written tool signatures. **Nothing in the field has a
   type-checked action surface.** "Does static typing on the tool interface
   reduce tool-error rate?" is a clean, novel, self-contained question with an
   obvious enterprise reading.
4. **Blast radius as a function of action interface.** WorkBench established
   side effects matter (29%/54%). CRMArena-Pro established agents leak data
   unless prompted. **Nobody has asked whether the action encoding changes the
   damage profile.** The mechanism is plausible and specific: batching converts
   one bad judgment into N bad writes.
5. **The programmatic anti-leakage guarantee.** τ-bench got uniqueness by hand;
   τ² got it by composition; you get it by construction *and* verify it
   empirically every build with `audit.py` + `cheater.py`. Against the 2026
   backdrop where all 8 major benchmarks were gameable, a benchmark shipping its
   own guessing-floor regression test is a real methodological contribution.

### The reframed pitch

> Every agent benchmark fixes the action interface and varies the model.
> Agent-Diff names the interaction-model axis explicitly and then picks one
> point on it. We hold task, world, tools, grader and trust boundary constant
> and vary only the action interface — across four surfaces, at tool-catalog
> sizes from 17 to 500 — and report not just accuracy but cost per successful
> task, reliability at k, and blast radius. The result is not "code wins"; it is
> the crossover surface: where each interface wins, at what catalog size, at
> what cost, and with what containment.

That is a paper. "An enterprise benchmark for CRM tasks" is not — CRMArena-Pro
already is one, at 40× your data scale.

---

## 10. Concrete changes this implies

Additions to the STRATEGY.md roadmap, in priority order:

1. **Read Agent-Diff in full**, adopt its design-space table as your related-work
   frame, and adopt `Score/$` + Bayesian CrIs. *(1 day)*
2. **Drop "enterprise benchmark" as the primary framing.** Primary = controlled
   study of agent action interfaces. Enterprise = the reporting layer. This
   resolves lab-mate critique #1 and #4 more cleanly than anything in the
   original strategy doc.
3. **`--n-trials` + pass^k using τ-bench's exact estimator.** Non-negotiable —
   every neighbour reports multi-trial numbers or CIs; single-trial results will
   not survive review. *(2 days)*
4. **`--catalog-size` sweep**, motivated by τ-bench's 95.9%-of-cost-is-input
   finding and Agent-Diff's docs-dilution ablation. *(3 days)* ← still the money
   experiment, now with two published papers pointing straight at it
5. **Templates: 15 → 40+.** WorkBench has 69. This is your weakest number and
   the easiest to fix given the DSL you already have. *(ongoing)*
6. **Add an unenforced `policy.md` layer** to the CRM scenario (τ-bench style)
   and measure policy compliance per surface. *(2 days)* ← highest-novelty
   cheap addition
7. **Hand-audit ~50 failed episodes and publish your evaluator–human agreement
   rate**, defending against the exact-match brittleness the 2026 validity audit
   documents. *(1 day)* ← cheapest credibility win available
8. **Frontier models.** Agent-Diff runs 9; τ-bench 12; CRMArena-Pro 9. You run 7
   local OSS models and no frontier model at all. *(2 days + credits)*

---

## Sources

**Read in full (PDF text extracted):** τ-bench · τ²-bench · Agent-Diff · Beyond Accuracy

- [τ-bench (arXiv 2406.12045)](https://arxiv.org/abs/2406.12045) · [τ²-Bench (arXiv 2506.07982)](https://arxiv.org/pdf/2506.07982) · [tau2-bench repo](https://github.com/sierra-research/tau2-bench)
- [CRMArena (arXiv 2411.02305)](https://arxiv.org/abs/2411.02305) · [CRMArena-Pro (arXiv 2505.18878)](https://arxiv.org/html/2505.18878v1) · [Salesforce blog](https://www.salesforce.com/blog/crmarena-pro/)
- [WorkBench (arXiv 2405.00823)](https://arxiv.org/abs/2405.00823)
- [WorkArena + BrowserGym (arXiv 2403.07718)](https://arxiv.org/html/2403.07718v2)
- [AppWorld (arXiv 2407.18901)](https://ar5iv.labs.arxiv.org/html/2407.18901) · [repo](https://github.com/StonyBrookNLP/appworld)
- [**Agent-Diff (arXiv 2602.11224)**](https://arxiv.org/abs/2602.11224) · [repo](https://github.com/agent-diff-bench/agent-diff) · [site](https://www.agentdiff.dev/)
- [CodeAct (arXiv 2402.01030)](https://arxiv.org/abs/2402.01030) · [repo](https://github.com/xingyaoww/code-act)
- [ToolSandbox (arXiv 2408.04682)](https://arxiv.org/abs/2408.04682) · [BFCL](https://openreview.net/pdf?id=2GmDdhBdDk)
- [MCP-Universe](https://mcp-universe.github.io/) · [MCP-Bench](https://github.com/Accenture/mcp-bench) · [MCPBench](https://github.com/modelscope/mcpbench) · [MCP-AgentBench](https://arxiv.org/pdf/2509.09734) · [MCPToolBench++](https://arxiv.org/pdf/2508.07575) · [MCP-RADAR](https://arxiv.org/pdf/2505.16700)
- [TheAgentCompany (arXiv 2412.14161)](https://arxiv.org/html/2412.14161v2) · [ITBench](https://github.com/itbench-hub/ITBench) · [ITBench-AA](https://huggingface.co/blog/ibm-research/itbench-aa) · [EnterpriseClawBench (arXiv 2606.23654)](https://arxiv.org/abs/2606.23654) · [OfficeBench](https://github.com/zlwang-cs/OfficeBench)
- [Agentic Benchmark Checklist (arXiv 2507.02825)](https://arxiv.org/abs/2507.02825) · [Validity Audit of Tool-Calling Evaluation (arXiv 2607.02577)](https://arxiv.org/html/2607.02577) · [How We Broke Top AI Agent Benchmarks](https://moogician.github.io/blog/2026/trustworthy-benchmarks-cont/) · [Log analysis is necessary](https://arxiv.org/pdf/2605.08545) · [Notation Matters (arXiv 2605.29676)](https://arxiv.org/abs/2605.29676)
