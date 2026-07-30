# Scope decision — split the study from the benchmark

Supersedes the positioning sections of `STRATEGY.md` (§0, §2, §3). The technical
recommendations there still stand; the framing changes.

Date: 2026-07-23

---

## The decision

Two projects, run **sequentially**, not in parallel:

- **Study A — "Action Interfaces for Tool-Using Agents"** (now, ~6–8 weeks)
  A controlled comparison: MCP-style structured calls vs code-mode, everything
  else held constant. This is the paper.
- **Project B — an enterprise benchmark** (later, conditional)
  Only if Study A produces a result an enterprise would pay to reproduce on
  their own catalog. See §5 for the trigger.

---

## 1. Separation means claims, not codebases

**Do not fork the repo.** One engine, two papers.

A second repo doubles maintenance, splits your test suite, and guarantees the
two drift. What you are separating is the *claim* and the *audience*, not the
code. Concretely:

- One harness, one scenario system, one verifier, one CSV.
- The "enterprise" layer was always going to be a **renderer over that CSV** —
  a report card, not a different benchmark. Delete the renderer for now; the
  columns it would read stay in the CSV.
- Project B, when it comes, is *new scenarios + new reporting* on the same
  engine. Nothing you build for Study A gets thrown away.

If you catch yourself designing "how do the two repos share code," stop — that's
the wrong problem.

---

## 2. What separation deletes (the good news)

Three of the five lab critiques evaporate the moment the enterprise claim goes:

| Critique | Status after separation |
|---|---|
| #1 "What's the purpose?" | ✅ Resolved. One question, stated in one sentence. |
| #2 "No real cases — do Zillow/Walmart" | ✅ **Void.** A controlled study needs *control*, not brand realism. One well-built domain is correct; a second is for generalization only. |
| #3 "Who is the end user?" | ✅ Resolved. Researchers and agent-framework authors. No BYO-catalog mode needed. |
| #4 "Output unclear — generic vs enterprise" | ✅ Resolved. One report. |
| #5 "Easy to add scenarios" | ⚠️ **Still applies, downgraded.** Not a product requirement anymore, but you need a 2nd domain to show the result generalizes, and reviewers will ask. Do the manifest refactor; skip `new-scenario` scaffolding and `SCENARIOS.md`. |

That is a large scope reduction. `retail_ops` drops from "must be enterprise-realistic
with volume and irreversibility and policy" to "a second domain, different shape,
enough to show the finding isn't CRM-specific."

---

## 3. ⚠️ The one thing you must NOT cut

**Cost stays. It is not an enterprise nicety — it is the dependent variable.**

The entire published claim for code-mode is a *cost* claim: 98.7% token
reduction (Anthropic), 92.8% at 500+ tools (Bifrost), 30% fewer steps (CodeAct).
τ-bench measured that **95.9% of agent cost is the input prompt carrying tool
schemas**, at only 15 tools.

A "code vs MCP" study that reports accuracy but not cost has not tested the
claim under examination. If you drop cost accounting because it *feels*
enterprise-flavored, you gut the paper. Same for the sandbox-compute term —
code-mode moves cost from tokens to compute, and a reviewer will catch you if
you price only one side.

**Rule of thumb for what survives the cut:** keep a metric if it is needed to
*test the hypothesis*; cut it if it only helps someone *make a purchase*.

| Metric | Verdict | Why |
|---|---|---|
| Tokens in/out | ✅ Keep | The mechanism |
| Cost $ (incl. sandbox seconds) | ✅ **Keep** | The dependent variable |
| Cost per successful task | ✅ Keep | Cost and accuracy must be joined; a cheap wrong answer is not cheap |
| pass^k, CIs, `--n-trials` | ✅ Keep | Basic rigor; every neighbour reports it |
| Unauthorized-write rate | ✅ Keep | Novel finding, not a buyer's metric |
| Tool-calls, turns, error taxonomy | ✅ Keep | Mechanism decomposition |
| Catalog-size sweep | ✅ Keep | The core experiment |
| Latency p50/p95 | 🔸 Keep the raw seconds, skip the percentile reporting | Cheap to record, not load-bearing |
| **Enterprise Readiness Card** | ❌ Cut | Pure Project B |
| **BYO-catalog mode** | ❌ Cut | Pure Project B |
| **`new-scenario` scaffold, SCENARIOS.md** | ❌ Cut | Adoption tooling, not science |
| **3 domain archetypes** | ❌ Cut to 2 | Generalization needs 2, not 3 |
| **CLASSic / procurement framing** | ❌ Cut | Wrong audience |

---

## 4. Study A — scope lock

**The question, in one sentence:**

> Holding task, world, tool implementations, grader, trust boundary and turn
> budget constant, how does the agent's *action interface* — structured tool
> calls vs generated code — affect success, cost, reliability, and blast radius,
> and how does that change with tool-catalog size?

**Independent variables (3):** action surface (python / js / ts / json_mcp) ×
tool-catalog size (17 / 50 / 150 / 500) × model.

**Held constant:** everything else. This is the contribution — say so explicitly
in the methods section, because it is the thing every neighbouring benchmark
fails to do.

**In scope**

1. `--n-trials` + pass^k (τ-bench's unbiased estimator) + bootstrap CIs
2. Cost accounting incl. sandbox compute; CPST
3. `--catalog-size` distractor-tool padding + the crossover curve
4. Single-source tool schemas (5 → 1) + skew test — *this one is now
   safety-critical, not hygiene: a schema skew between surfaces silently
   invalidates the entire study*
5. `unauthorized_write_rate` promoted out of the `forbidden` check
6. The **one-tool-call-per-`execute()` ablation** — separates "code-mode helps
   because reasoning" from "code-mode helps because batching." Without it a
   reviewer can dismiss the whole result.
7. Frontier models + finish the Anthropic wire format
8. Templates 15 → 40+
9. Scenario manifest refactor + one second domain
10. Hand-audit ~50 failed episodes; publish evaluator–human agreement rate

**Explicitly out of scope** — write this list down and defend it: enterprise
report cards, procurement framing, BYO-catalog, brand-realistic domains, a third
domain, adoption tooling, leaderboard hosting.

---

## 5. Project B — the trigger condition

Don't plan it now. Plan the *decision* to start it.

Start Project B only if Study A shows **a crossover that depends on something an
enterprise controls** — catalog size, task volume, risk tolerance. If the answer
turns out to be "code-mode wins everywhere" or "it's a wash," there is no
enterprise product, because there is no decision left to support. You'd be
building a tool to answer a question with a known answer.

That is a real possible outcome, and it is fine. **Study A may simply be the
contribution.** Treat Project B as an option you're buying, not a commitment
you're deferring.

If the trigger does fire, Project B = same engine + domain archetypes with
volume/irreversibility/policy + the readiness card + BYO-catalog. All the
`STRATEGY.md` material is still valid then; nothing is wasted.

---

## 6. Housekeeping

- **Rename.** `Ent-Agent-Bench` currently advertises a claim you're dropping.
  The repo name is the first thing a reviewer reads. Something like
  `action-surface-bench` / `ASB`, or keep the directory and change the paper
  title and README H1 — but don't leave "Ent-" fronting a study that isn't
  enterprise-scoped.
- **README rewrite**, first paragraph = the one-sentence question in §4.
- **Keep `STRATEGY.md` and `RELATED_WORK.md`.** The related-work analysis is
  unchanged by this decision — arguably strengthened, since §9 of that doc found
  your defensible novelty was the action-interface comparison all along.
- **Frame the related work using Agent-Diff's design-space table** (interaction
  model / environment / evaluation signal / observability / horizon).
  Ent-Agent-Bench is the row that varies interaction model. That framing only
  works once the enterprise claim is gone — another argument for this split.

---

## 7. This week

1. Rename + rewrite the README around the single question. *(half day)*
2. Write the scope-lock list from §4 into the repo and stop negotiating with it.
3. Read Agent-Diff (2602.11224) in full.
4. Start on `--n-trials` + cost accounting — they unblock every result table.
