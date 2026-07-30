# Ent-Agent-Bench — Strategy Review

Response to the five critiques raised in lab review, grounded in what the code
currently does and in what the surrounding benchmark literature already covers.

Date: 2026-07-23

---

## 0. TL;DR

Your lab mates are right, but not for the reason they stated. They gave you five
symptoms of **one** root cause:

> The project is currently two different products wearing one name — a
> *scientific* benchmark answering "does code-mode beat JSON tool-calling?", and
> an *enterprise decision tool* answering "which agent architecture should I
> deploy?". Neither is finished, because every design decision has been split
> between them.

The fix is not to pick one and throw away the other. It is to **separate the
engine from the report**:

| Layer    | Name                          | Question it answers                                                                                                     | Audience                              |
| -------- | ----------------------------- | ----------------------------------------------------------------------------------------------------------------------- | ------------------------------------- |
| Engine   | `agent-bench-core`          | Under identical tasks/data/grading, how do action surfaces compare?                                                     | You, reviewers, paper                 |
| Report A | *Code-Mode Study*           | Does code-mode beat MCP-style calls, and where does the crossover sit?                                                  | Research (the paper)                  |
| Report B | *Enterprise Readiness Card* | For**my** workflow and **my** tool catalog, what is cost/latency/reliability/blast-radius per architecture? | Platform / AI-infra team at a company |

Everything below is how to get there. The good news: your harness is already
~70% of the engine. The template DSL is genuinely better than most published
alternatives. What is missing is (a) the metrics enterprises actually buy on,
(b) a scenario plug-in boundary, (c) frontier models, (d) a scaling axis.

---

## 1. What you already have (be honest about the strengths — they're real)

Reading the code, not the README:

- **Fair-by-construction comparison.** Executor container has *zero* filesystem
  access to the DB; code-mode reaches data only via HTTP to the same tool-server
  `json_mcp` uses. This is the single hardest thing to get right in a code-vs-
  tools comparison, and you got it right. Most blog-post "benchmarks" of code
  mode do not control for this.
- **Constructive world generation.** `world_builder.py` builds the world *from*
  the task rather than sampling a world and hoping a task is valid. Identity
  reservation + reference partitioning + anti-fingerprint id interleaving.
- **`cheater.py` as a permanent regression test.** A guessing-floor baseline
  that fails the corpus if construction starts leaking. This directly answers
  the class of attack in *"How We Broke Top AI Agent Benchmarks"* (Wang et al.,
  2026), which showed **all eight** of SWE-bench, WebArena, OSWorld, GAIA,
  Terminal-Bench, FieldWorkArena and CAR-bench could be scored near-perfectly
  without solving anything. You are ahead of the published field here. Say so
  loudly — it is your strongest differentiator and you are currently burying it.
- **Six-check grading with a `forbidden` check.** You already measure
  *unauthorized writes*. You just aren't reporting it as a safety metric (see §4).
- **A real YAML task DSL** (`template_interpreter.py`, 287 lines) with
  `for_each`, `@refs`, `sim_date_offset`, guards. Adding a task type is already
  one file. Your lab mates' "easy to add scenarios" critique is about
  **scenarios**, not tasks — and they're right, but the gap is smaller than it
  looks (§6).
- **The fixed 20-turn budget rationale.** Correct and defensible; keep it and
  keep the paragraph that defends it.

Do not rewrite any of this. The work below is additive.

---

## 2. Critique #1 — "What is the purpose? It's promoted as enterprise but doesn't serve enterprises"

### The diagnosis

Your outputs today are `passed`, `fulfillment_score`, `tool_calls_made`,
`model_turns`, tokens, latency, error buckets. That is a *research* output
vector. An enterprise platform lead cannot make a decision from it, because the
three numbers they need are missing:

1. **What does one successfully completed task cost me, in dollars?**
2. **If I run it 10 times, how often does it work — all 10 times?**
3. **When it fails, what does it break?**

The literature is blunt about this. From the CPST work: *cost is entirely
ignored in traditional benchmarks; despite agents making hundreds of API calls
per task, no major benchmark reports cost metrics*, with observed **50×** cost
spreads ($0.10–$5.00/task) at comparable accuracy. The vendor-side framing that
has actually landed with buyers is Aisera's **CLASSic** — Cost, Latency,
Accuracy, Stability, Security. Automation Anywhere built an in-house
`GBA-Bench` across seven business domains for exactly this reason.

### The decision to make

Don't drop "enterprise". Redefine it as a **reporting contract**, not a
scenario theme. "Enterprise" should mean: *this benchmark reports the five
things an enterprise buyer must sign off on, per architecture, per model.*
Enterprise-ness lives in the **metrics and the report card**, not in whether
the fake company is called Acme or Walmart.

That single reframing resolves critiques #1 and #4 simultaneously.

---

## 3. Critique #3 — "Who is the end user, and how do they use it?"

Pick **one** primary. My recommendation, with reasoning:

| Candidate user                                                                                                     | What they'd do with it                                                                                                                              | Verdict                                                                                              |
| ------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| **Enterprise AI-platform / agent-infra engineer** deciding how to expose ~50–500 internal tools to an agent | Runs the harness against*their* tool catalog; gets a per-architecture cost/reliability/blast-radius card; decides MCP-direct vs code-mode gateway | ✅**Primary.** Real, unserved, has budget, and the decision is genuinely open today            |
| Model vendor / research lab                                                                                        | Cites your paper for the code-vs-JSON finding                                                                                                       | ✅ Secondary — free, comes with the paper                                                           |
| Business/domain owner (a sales ops lead)                                                                           | Wants "will an agent do my CRM job?"                                                                                                                | ❌ Not you — that's CRMArena-Pro's lane, and Salesforce has a 25-object sandbox you cannot outbuild |

**Write the user story into the README as the first paragraph.** Something like:

> You are the platform engineer at a company with 200 internal tools behind an
> MCP gateway. You must decide whether your agents call those tools directly as
> structured calls, or write sandboxed code against them. That decision changes
> your token bill by an order of magnitude and your failure modes qualitatively.
> Ent-Agent-Bench answers it with your workload, not a vendor's demo.

And define the **usage mode** concretely — this is the part currently missing:

- **Mode A (leaderboard/read-only):** they read your published results. Cheap
  for them, low value.
- **Mode B (BYO-catalog):** ← this is the product. They point the harness at
  their own OpenAPI/MCP tool catalog, it auto-generates a scenario skeleton, they
  write N task templates in your YAML DSL, they get their own report card.

Mode B is only possible if §6 (scenario plug-in boundary) is done. That's why
critique #5 and critique #3 are the same critique.

---

## 4. Critique #4 — "The output isn't clear: generic code-vs-MCP vs enterprise metrics"

Your lab mates are correct that these should be two report surfaces over one
run. Here is the concrete metric plan.

### 4.1 Keep (already implemented)

`passed`, `answer_correct`, `db_correct`, `fulfillment_score`,
`tool_calls_made`, `model_turns`, `input/output_tokens`,
`model/execution/total_latency_seconds`, the five error buckets, `recovered`,
`hit_turn_budget`, the three infra flags.

### 4.2 Add — Cost (C)

Currently `meter.py` records tokens but never money. Add a price table and
derive:

```
episode_cost_usd = in_tok * price_in  + out_tok * price_out
                 + exec_seconds * compute_price   # code-mode's sandbox is NOT free
```

The `exec_seconds` term matters enormously and is the term every code-mode blog
post omits. Code-mode moves cost from tokens to compute; if you don't price the
sandbox you will overstate its advantage and an enterprise reviewer will catch it.

Then the headline number:

```
CPST  =  total_cost_over_all_attempts / number_of_successful_episodes
       = mean_episode_cost / pass_rate
```

**Cost per successful task is your single best headline metric.** It is the one
number that is simultaneously rigorous, novel for this comparison, and directly
actionable for a buyer.

Implementation: add `pricing:` to each `models.yaml` entry
(`price_in_per_mtok`, `price_out_per_mtok`), plus a
`config.SANDBOX_USD_PER_SECOND`. For local llama.cpp models, price them at
measured GPU-hour cost so local and API models land on one axis — that
comparison alone is a publishable finding.

### 4.3 Add — Stability / reliability (S)

You currently run each (model, surface, task) **once**. That means every number
you have is a single sample and you cannot report a confidence interval. This is
the most serious *scientific* gap in the project right now, independent of the
enterprise framing.

Add `--n-trials K` (default 1, paper runs at K≥5) and report:

- `pass@1` — mean pass rate (what you have today)
- **`pass^k`** — probability all *k* independent attempts succeed. τ-bench
  introduced this precisely because it is what production cares about; it decays
  as p^k, so a 90% agent is 57% reliable at k=8.
- **`variance` / bootstrap 95% CI** on pass rate and on cost.

Hypothesis worth stating up front: *code-mode has higher pass@1 but higher
variance*, because a single unhandled exception kills a whole batched turn — the
GitHub-CLI-vs-MCP-vs-code-mode comparison found exactly this failure mode (code
mode won 5/5 on CI-investigation tasks but failed 4/5 on nonexistent-repo tasks,
where scripts threw instead of gracefully reporting). If you can show a
**reliability/efficiency tradeoff curve** between the two architectures, that is
your paper's contribution, not the token count.

### 4.4 Add — Security / blast radius (S)

You already compute this and throw it away. `verify.py`'s `forbidden` check
knows exactly when the agent wrote a row it was not authorized to touch.
Promote it:

- `unauthorized_write_count` — how many rows outside the allowed set changed
- `unauthorized_write_rate` — fraction of episodes with ≥1
- `destructive_action_count` — deletes / irreversible ops (add a few such tools)

This is enterprise gold and nobody in the code-mode-vs-MCP conversation is
measuring it. The a priori story is compelling: **code-mode's advantage is
batching, and batching is exactly what turns one bad decision into fifty bad
writes.** If your data shows code-mode has higher throughput *and* larger blast
radius per failure, that is a genuinely important, quotable enterprise result.

### 4.5 Add — Latency (L), reported the way ops teams read it

Not a mean. Report `p50 / p95` of `total_latency_seconds`, and split
*time-to-first-effect* from *time-to-completion*. Note the known result that
code-mode is often the **slowest** wall-clock condition (43.4s avg in the
CLI/MCP/code-mode comparison) despite being the cheapest — cost and latency
point in opposite directions here, which is precisely the tradeoff an enterprise
must be shown rather than told.

### 4.6 Add — the missing independent variable: **tool-catalog size**

This is the biggest single gap and the easiest high-impact fix.

The entire economic argument for code-mode is that structured tool-calling
carries every schema in context on every turn, so its cost grows with catalog
size while code-mode's does not (progressive disclosure). Anthropic's own
figure — 150k → 2k tokens — is a *500-tool-scale* claim. Bifrost measures 92.8%
input-token reduction **at 500+ tools**.

**You are testing at 17 tools.** At 17 tools, code-mode's headline advantage
barely exists. You are measuring the comparison at the one point on the curve
where it is least interesting, and an enterprise with 300 tools cannot map your
result onto their situation.

Fix: add a `--catalog-size {17, 50, 150, 500}` dial that pads the exposed tool
catalog with realistic, plausible-but-irrelevant distractor tools (auto-generated
from the schema patterns in `tool_server/models.py`; they don't need real
implementations, only schemas + a stub route, since correct solutions never call
them). Then plot **cost and pass-rate vs catalog size, per surface.**

That plot — *where is the crossover point at which code-mode starts winning?* —
is the single most valuable artifact this project can produce. It is what an
enterprise actually needs, it is publishable, and it makes the "generic vs
enterprise" tension disappear: the same curve is a scientific result **and** a
procurement input.

### 4.7 The two report surfaces

One run → one CSV → two renderers (extend `analysis/`):

**A. Research report** (paper figures): pass rate by surface × difficulty ×
model; turns/tool-calls; error taxonomy; cost & catalog-size scaling curves;
pass^k.

**B. Enterprise Readiness Card** (one page per architecture, per model):

```
Architecture: code-mode (Python)      Model: claude-...      Catalog: 150 tools
──────────────────────────────────────────────────────────────────────────────
Accuracy        task success           78%   (95% CI 74–82)
Stability       pass^5                 41%          ← run-to-run consistency
Cost            per successful task    $0.041       ← 3.1× cheaper than JSON-MCP
Latency         p50 / p95              14s / 51s    ← 1.4× slower than JSON-MCP
Security        unauthorized-write rate 3.2%        ← 2.6× higher than JSON-MCP
Ops             hit turn budget         4%
                recovered from error   61%
──────────────────────────────────────────────────────────────────────────────
Verdict: cheaper and more capable at this catalog size; costs you consistency
         and containment. Recommended with write-scoping + dry-run review.
```

That card is the deliverable that makes the word "enterprise" honest.

---

## 5. Critique #2 — "No real cases; do Zillow / Walmart / Amazon / eBay"

Take the **spirit** of this and reject the **letter**.

### Why the letter is wrong

1. **Legal/IP.** Naming Walmart or Zillow in a published benchmark, with
   invented schemas and invented business policies, invites trademark and
   misrepresentation problems, and any result reads as a claim about that
   company's systems. Salesforce could build CRMArena on Salesforce schemas
   because it is Salesforce.
2. **You cannot get the real thing.** Real enterprise schemas are the most
   guarded artifact a company has. What you'd actually build is "our guess at
   Walmart" — which is *no more real* than what you have now, just more
   legally exposed and harder to defend in review.
3. **Maintenance.** Real-world-tethered benchmarks rot. MCP-Universe hits live
   servers and pays for it in flakiness.

### Why the spirit is right

The real complaint is: **your one domain is small, shallow, and doesn't exercise
enterprise-characteristic difficulty.** That is true and it is fixable. Your CRM
has 6 tables, 17 tools, 15 templates. Real enterprise workflows have:

- **cross-system boundaries** (CRM ↔ ERP ↔ ticketing — different auth, partial
  failures, no joins)
- **written policy the agent must obey**, not just data to fetch (τ-bench's
  `policy.md`; CRMArena-Pro makes policy compliance a first-class skill)
- **irreversibility** (refunds, cancellations, sends)
- **volume** — the enterprise-defining property. A task over 3 rows and a task
  over 3,000 rows are different tasks, and **volume is where code-mode should
  dominate**, since JSON-MCP can't loop.
- **large tool catalogs** (§4.6)
- **ambiguity and required clarification**

### What to build instead

Three **archetype domains** — generic, unbranded, but structurally faithful to a
recognizable enterprise category. Publish the schema derivations from public
sources (public API docs, published data models) so realism is auditable.

| Domain                   | Archetype (say this, not the brand)                                                      | Enterprise property it adds                                         |
| ------------------------ | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| `crm_scenario`         | *(have it)* B2B sales pipeline                                                         | multi-hop lookup, per-item branching                                |
| `retail_ops`           | "a large-catalog retailer's order/returns/inventory back-office" (Walmart/Amazon-shaped) | **volume + irreversible actions + written refund policy**     |
| `marketplace_listings` | "a listings marketplace's inventory/pricing/compliance ops" (Zillow/eBay-shaped)         | **cross-system**, geo/temporal constraints, policy compliance |

Add exactly **one** (`retail_ops`) before the paper. Two domains proves the
harness generalizes; three is a v2 problem. Choose retail because it gives you
volume and irreversibility, the two properties most likely to *flip* the
code-vs-MCP result — which is scientifically the most interesting outcome.

Frame it in the paper as: *"domains are structural archetypes derived from
public data models of $CATEGORY, not simulations of any specific company."*
That is defensible in review and safe legally, and it answers the critique.

---

## 6. Critique #5 — "It must be very, very easy to add scenarios"

### Current state (measured, not guessed)

Coupling to `crm_scenario` outside its own package is **6 real import sites**:

| File                                | Coupling                                                              |
| ----------------------------------- | --------------------------------------------------------------------- |
| `src/tool_server/services.py:5`   | `import crm_tools as impl` — the whole tool implementation binding |
| `src/agent/prompts.py:9,49`       | imports`SIM_TODAY`; hardcodes `_TOOLS_JSON["crm_tools"]`          |
| `src/agent/loop.py:29,62,229,254` | `_call_crm_tool_directly`, `crm_db.TABLES` for the diff           |
| `main.py:10`                      | imports`build_tasks` from the CRM package                           |
| `src/tests/*` (4 files)           | test imports                                                          |
| `docker/tool-server.Dockerfile`   | bakes the scenario in                                                 |

That is **good news**: the architecture is already almost scenario-agnostic
(`db/db.py` is explicitly scenario-agnostic; the tool-server is generic HTTP; the
executors know nothing). This is a ~2–3 day refactor, not a rewrite.

### Target: a scenario is a directory, and nothing outside it knows its name

```
src/db/scenarios/<name>/
  scenario.yaml          ← the manifest (NEW — the whole contract)
  schema.py              ← tables + SIM_TODAY
  tools.py               ← tool implementations
  tools.schema.json      ← generated, not hand-written (see below)
  pools.py               ← random draw pools
  tasks/templates/<tier>/*.yaml
  tasks/frozen/           ← generated
```

`scenario.yaml`:

```yaml
name: retail_ops
sim_today: "2026-06-01"
tables: [orders, order_items, returns, inventory, customers, policies]
tools_module: tools
policy_doc: policy.md          # optional; injected into the system prompt
tiers: [easy, medium, hard, expert]
```

Then:

- `services.py` → `importlib` the module named in the manifest.
- `prompts.py` / `loop.py` → take a `Scenario` object; `SIM_TODAY` and `TABLES`
  come from it.
- `main.py` / `cli.py` → `--scenario retail_ops` (default `crm_scenario`), and
  `generate-tasks --scenario`.
- `tool-server.Dockerfile` → mount the scenario dir rather than baking it.
- Results paths → `results/<scenario>/<model>/...`; add a `scenario` column to
  the CSV **now**, before you accumulate more results you'd have to migrate.

### Two force-multipliers for "very very easy"

**1. Generate the tool schemas, don't write them.** You maintain the tool
catalog in *three* places today: `tool_server/models.py` (Pydantic),
`agent/tools.json`, `agent/tools_python.pyi`, `agent/tools_js.js`, plus TS
`tools.d.ts`. For one scenario that's tolerable; for a contributor adding a
scenario it is five chances to introduce a silent skew between what code-mode
sees and what JSON-MCP sees — which would **invalidate your central comparison**.
Make Pydantic the single source and emit the other four at build time
(`main.py gen-schemas`). Add a test asserting all five agree. This is the
highest-value correctness fix in the whole document, because a schema skew is a
confound that would not show up as a crash — only as a wrong result.

**2. `main.py new-scenario <name>`** — scaffolds the directory, a 2-table toy
schema, 2 tools, 1 template, and a passing audit. Plus `SCENARIOS.md`: a
one-page "add a scenario in 30 minutes" walkthrough. τ²-bench's adoption is
largely down to its domain pack being a documented, self-contained folder
(`tasks.json` / `policy.md` / `db.json` / tests) — copy that pattern
deliberately.

### Acceptance test for this critique

> A lab mate who has never seen the repo can add a working 3-table scenario with
> 5 tools and 3 task templates, and get a green audit, in under one day, reading
> only `SCENARIOS.md`.

Make one of them actually try it before the paper. That's your real test.

---

## 7. Two gaps nobody raised, that reviewers will

### 7.1 No frontier models

`models.yaml` is seven local OSS models, 12B–72B. Your README already admits the
Anthropic path is untested end-to-end. This is fatal to the enterprise claim —
no enterprise is deciding their agent architecture based on Qwen2.5-14B — and
weak for the paper, since a result that holds only for small local models may be
an artifact of weak code generation rather than a property of the architectures.

Add at minimum one frontier model per major vendor via API, and **finish the
Anthropic wire-format path in `loop.py`** (currently `AnthropicClient`
normalizes responses but multi-turn message building assumes the OpenAI shape).
Budget an evening plus API credit. The local-model fleet then becomes a genuine
second contribution: *does the code-vs-MCP tradeoff invert at small scale?* —
and cost-normalized local-vs-API is an enterprise question people actually ask.

### 7.2 Validity threats you should pre-empt in writing

*Log analysis is necessary for credible evaluation of AI agents* (2026) reports
that **tool-use errors account for >50% of agent failures** and that scaffold
choices can swing SWE-bench results by 20 points. Your scaffold differs *by
design* between arms — that's the experiment — so you must show the difference is
the treatment and not an accident:

- Publish the exact system prompt per surface, and show token-count parity of
  the tool documentation across surfaces (a fatter Python `.pyi` than the JSON
  schema is a confound).
- Run an **ablation**: code-mode restricted to one tool call per `execute()`.
  If code-mode's advantage survives that, the advantage is *reasoning*; if it
  vanishes, the advantage is *batching*. That single ablation is what separates
  a real paper from a blog post, and it's cheap — a flag in the executor.
- Report `n_functions_expected` vs `tool_calls_made` as an efficiency ratio; you
  already collect both and don't use them together.
- Keep and publish the `cheater.py` baseline number next to every result table.

---

## 8. Proposed roadmap

Ordered by (impact × defensibility) / effort.

### Phase 1 — Make the claim honest (≈2 weeks)

1. `scenario` column in the CSV + cost fields in `meter.py`; `pricing:` in
   `models.yaml`; CPST in the analysis notebook. *(2d)*
2. `--n-trials` + pass^k + bootstrap CIs. *(2d)*
3. Promote `forbidden` → `unauthorized_write_rate`; add 2–3 destructive tools to
   the CRM. *(1d)*
4. `--catalog-size` distractor-tool padding + the scaling curve. *(3d)* ← **the
   money experiment**
5. p50/p95 latency in the analysis layer. *(0.5d)*
6. Rewrite README §1 around the platform-engineer user story. *(0.5d)*

### Phase 2 — Make it extensible (≈1.5 weeks)

7. Single-source tool schemas + skew test. *(2d)* ← highest correctness value
8. `scenario.yaml` manifest + de-hardcode the 6 import sites. *(3d)*
9. `new-scenario` scaffold + `SCENARIOS.md` + have a lab mate run the acceptance
   test in §6. *(2d)*

### Phase 3 — Make it credible (≈2 weeks)

10. Frontier models + finish the Anthropic path. *(2d)*
11. `retail_ops` domain: volume tasks, irreversible actions, a `policy.md` the
    agent must obey. *(5d)*
12. The one-tool-per-exec ablation. *(1d)*
13. Enterprise Readiness Card renderer. *(2d)*

### Phase 4 — Ship

14. Full matrix run; research report + card; `SCENARIOS.md` as the adoption path.

Phases 1 and 2 answer all five critiques. Phase 3 is what makes it publishable.

---

## 9. How to answer each critique in one sentence

Keep these for the next lab meeting:

1. **"What's the purpose?"** — It answers one architectural decision an
   enterprise platform team must make today (direct tool-calls vs sandboxed
   code over the same tool catalog) and reports it in the five terms they buy
   on: cost per successful task, reliability at k, accuracy, latency
   percentiles, and blast radius.
2. **"No real cases."** — Domains are unbranded structural archetypes derived
   from public data models, not simulations of named companies; we're adding a
   high-volume retail-ops archetype because volume and irreversibility are the
   properties most likely to flip the result.
3. **"Who's the end user?"** — The platform/AI-infra engineer who owns the tool
   gateway; they use it in BYO-catalog mode against their own tools, which is
   why the scenario plug-in boundary is a Phase-2 blocker and not a nice-to-have.
4. **"The output isn't clear."** — One run, two renderers: a research report for
   the paper and a per-architecture Enterprise Readiness Card for buyers.
5. **"Adding scenarios must be trivial."** — A scenario becomes one directory
   with a manifest, scaffolded by `main.py new-scenario`, with a stated
   acceptance test: a newcomer ships a working scenario in under a day.

And the sentence that reframes the whole project:

> The result an enterprise needs isn't "code-mode wins." It's **the crossover
> curve**: at what tool-catalog size, task volume, and risk tolerance does each
> architecture win — and what does each cost per successful task at that point.

---

## 10. Risks

- **Scope.** Phase 3's `retail_ops` will feel like the fun part and eat the
  schedule. Phases 1–2 are what the critiques actually demanded; do them first.
- **Field velocity.** Code-mode-vs-MCP is a hot, fast-moving topic with many
  low-rigor blog benchmarks. Your moat is rigor (fair sandbox, cheater baseline,
  ablation, CIs) — lean on it, and cite the blog numbers as the thing you're
  auditing rather than confirming.
- **Overlap.** Do not drift toward CRMArena-Pro's territory (agent capability on
  business tasks). Your axis is the *action surface*, held against everything
  else constant. That's a different paper and a defensible one.
- **Cost model disputes.** Pricing the sandbox and pricing local GPU time are
  both contestable. Publish the price table as a config file so reviewers can
  re-derive CPST under their own assumptions.

---

## Sources

- [CRMArena-Pro (arXiv 2505.18878)](https://arxiv.org/html/2505.18878v1) · [Salesforce writeup](https://www.salesforce.com/blog/crmarena-pro/)
- [τ-bench (arXiv 2406.12045)](https://arxiv.org/abs/2406.12045) · [τ²-Bench (arXiv 2506.07982)](https://arxiv.org/pdf/2506.07982) · [tau2-bench domain packs](https://github.com/sierra-research/tau2-bench)
- [MCP-Universe](https://mcp-universe.github.io/) · [MCP-Bench (Accenture)](https://github.com/Accenture/mcp-bench) · [MCPBench (ModelScope)](https://github.com/modelscope/mcpbench) · [MCP-AgentBench](https://arxiv.org/pdf/2509.09734)
- [CodeAct: Executable Code Actions Elicit Better LLM Agents (arXiv 2402.01030)](https://arxiv.org/abs/2402.01030)
- [Code Execution with MCP — token-cost analyses](https://www.getmaxim.ai/articles/code-execution-with-mcp-how-code-mode-cuts-agent-token-costs-by-90/) · [at 500+ tools](https://www.getmaxim.ai/articles/cutting-mcp-token-costs-by-92-at-500-tools/)
- [GitHub CLI vs MCP vs Tool Search vs Code Mode (measured head-to-head)](https://kunchenguid.medium.com/i-benchmarked-github-cli-vs-mcp-vs-tool-search-vs-code-mode-turns-out-the-best-solution-is-none-93528d5039e4)
- [How We Broke Top AI Agent Benchmarks](https://moogician.github.io/blog/2026/trustworthy-benchmarks-cont/) · [Agentic Benchmark Checklist (arXiv 2507.02825)](https://arxiv.org/abs/2507.02825) · [Log analysis is necessary for credible evaluation](https://arxiv.org/pdf/2605.08545)
- [Cost per Successful Task](https://langwatch.ai/blog/cost-per-successful-task) · [Beyond Accuracy: multi-dimensional enterprise agent evaluation (arXiv 2511.14136)](https://arxiv.org/pdf/2511.14136) · [CLASSic framework](https://aisera.com/blog/enterprise-ai-benchmark/) · [GBA-Bench](https://www.automationanywhere.com/company/blog/product-insights/ai-agent-benchmark)
- [TheAgentCompany (arXiv 2412.14161)](https://arxiv.org/html/2412.14161v2) · [AppWorld](https://benchmarkingagents.com/appworld-benchmark/)
