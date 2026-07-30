# build_notebook.py — generates benchmark_analysis.ipynb. Not part of the
# harness itself; a one-off build script kept around so the notebook's cells
# can be regenerated/edited as code instead of hand-editing raw ipynb JSON.
# Run: python3 build_notebook.py
from __future__ import annotations

import json
import uuid
from pathlib import Path

CELLS = []


def md(text: str) -> None:
    CELLS.append({"cell_type": "markdown", "metadata": {}, "id": uuid.uuid4().hex[:8],
                  "source": text.splitlines(keepends=True)})


def code(text: str) -> None:
    CELLS.append({"cell_type": "code", "metadata": {}, "execution_count": None, "id": uuid.uuid4().hex[:8],
                  "outputs": [], "source": text.splitlines(keepends=True)})


md("""\
# action-surface-bench — Results Analysis

Analyzes every model's benchmark results under `results/<model>/<model>.csv` \
— first model by model, then aggregated across the whole fleet. The \
aggregated section covers the core comparison this benchmark exists to \
make: **code-mode (Python/JS/TS) vs structured JSON/MCP tool-calling**.

Run the benchmark first (e.g. `./run_full_benchmark.sh`) so the CSVs exist, \
then run this notebook top to bottom.""")

code("""\
import glob
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from IPython.display import Markdown, display

pd.set_option("display.precision", 3)
plt.rcParams["figure.figsize"] = (8, 4)""")

code("""\
RESULTS_DIR = Path("../results")

csv_paths = sorted(RESULTS_DIR.glob("*/*.csv"))
if not csv_paths:
    raise FileNotFoundError(
        f"no CSVs found under {RESULTS_DIR.resolve()} -- run the benchmark first "
        "(e.g. ./run_full_benchmark.sh) so results/<model>/<model>.csv exist."
    )

df = pd.concat((pd.read_csv(p) for p in csv_paths), ignore_index=True)
df = df.dropna(how="all")  # guard against a stray blank trailing row

# A clean run is one that actually completed the episode loop -- infra/model-API/
# episode-level errors are harness or serving-setup problems (e.g. a request
# landing while the model was still loading), not a genuine task failure, and
# would otherwise silently drag a model's pass rate down for reasons that have
# nothing to do with its actual task-solving ability.
df["clean_run"] = ~(
    df["infra_error"].astype(bool)
    | df["model_api_error"].astype(bool)
    | df["episode_error"].astype(bool)
)
df["code_mode"] = df["surface"].isin(["python", "js", "ts"])

print(f"loaded {len(df)} episodes across {df['model'].nunique()} model(s): {sorted(df['model'].unique())}")
print(f"clean runs: {df['clean_run'].sum()} / {len(df)} ({df['clean_run'].mean():.1%})")""")

md("""\
## Per-Model Analysis

For each model: pass rate by surface and by difficulty tier, error profile, \
and efficiency (turns, tool calls, tokens, latency). Episodes that hit a \
harness/infra-level error are called out and excluded from the pass-rate \
numbers below them, so a serving hiccup doesn't get counted as a task \
failure.""")

code("""\
SURFACE_ORDER = ["python", "js", "ts", "json_mcp"]
DIFFICULTY_ORDER = ["easy", "medium", "hard", "expert"]

for model in sorted(df["model"].unique()):
    display(Markdown(f"### {model}"))
    sub = df[df["model"] == model]
    clean = sub[sub["clean_run"]]

    n_dirty = len(sub) - len(clean)
    if n_dirty:
        display(Markdown(
            f"*{n_dirty} of {len(sub)} episodes hit an infra/model-API/episode-level "
            f"error (harness or serving issue, not a task failure) -- excluded from "
            f"the pass rates below.*"
        ))

    display(Markdown("**Pass rate by surface**"))
    display(clean.groupby("surface")["passed"].agg(["mean", "count"])
            .rename(columns={"mean": "pass_rate", "count": "n"})
            .reindex(SURFACE_ORDER))

    display(Markdown("**Pass rate by difficulty**"))
    display(clean.groupby("difficulty")["passed"].agg(["mean", "count"])
            .rename(columns={"mean": "pass_rate", "count": "n"})
            .reindex(DIFFICULTY_ORDER))

    display(Markdown("**Efficiency by surface (means)**"))
    display(clean.groupby("surface")[
        ["model_turns", "tool_calls_made", "total_tokens", "total_latency_seconds"]
    ].mean().reindex(SURFACE_ORDER))

    error_cols = ["tool_error_count", "syntax_error_count", "type_error_count",
                  "runtime_error_count", "parse_error_count"]
    display(Markdown("**Error profile (total counts across all episodes)**"))
    display(clean[error_cols].sum().rename("total"))

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    clean.groupby("surface")["passed"].mean().reindex(SURFACE_ORDER).plot.bar(
        ax=axes[0], title=f"{model}\\npass rate by surface", ylim=(0, 1))
    clean.groupby("difficulty")["passed"].mean().reindex(DIFFICULTY_ORDER).plot.bar(
        ax=axes[1], title=f"{model}\\npass rate by difficulty", ylim=(0, 1))
    for ax in axes:
        ax.set_ylabel("pass rate")
        ax.tick_params(axis="x", rotation=0)
    plt.tight_layout()
    plt.show()""")

md("## Aggregated Cross-Model Analysis")

md("### Overall pass rate by model")

code("""\
clean = df[df["clean_run"]]

overall = (clean.groupby("model")["passed"].agg(["mean", "count"])
           .rename(columns={"mean": "pass_rate", "count": "n"})
           .sort_values("pass_rate", ascending=False))
display(overall)

fig, ax = plt.subplots(figsize=(9, 4))
overall["pass_rate"].plot.barh(ax=ax)
ax.set_xlabel("pass rate")
ax.set_xlim(0, 1)
ax.set_title("Overall pass rate by model (clean runs only)")
plt.tight_layout()
plt.show()""")

md("""\
### The core question: code-mode vs json_mcp

Every task ran through both styles: writing code (`python`/`js`/`ts`) versus \
emitting structured JSON/MCP tool calls. This is the comparison the whole \
benchmark exists to make.""")

code("""\
code_vs_structured = (
    clean.groupby(["model", "code_mode"])["passed"]
    .mean()
    .unstack()
    .rename(columns={True: "code_mode (py/js/ts avg)", False: "json_mcp"})
)
display(code_vs_structured)

ax = code_vs_structured.plot.bar(figsize=(10, 5))
ax.set_ylabel("pass rate")
ax.set_ylim(0, 1)
ax.set_title("Code-mode vs json_mcp pass rate, by model")
ax.legend(title="")
plt.tight_layout()
plt.show()""")

md("""\
### Code-mode vs json_mcp, by model AND difficulty tier

Does the gap narrow (or reverse) on harder tiers, where code-mode's ability \
to batch several tool calls into one `execute()` turn should matter most? \
One grid cell per model: difficulty tier on the x-axis, code-mode vs \
json_mcp pass rate side by side.""")

code("""\
tier_pivot = (
    clean.groupby(["model", "difficulty", "code_mode"])["passed"]
    .mean()
    .unstack("code_mode")
    .rename(columns={True: "code_mode", False: "json_mcp"})
    .reindex(DIFFICULTY_ORDER, level="difficulty")
)
display(tier_pivot)""")

code("""\
models_sorted = sorted(clean["model"].unique())
n = len(models_sorted)
ncols = 2
nrows = -(-n // ncols)  # ceil division

fig, axes = plt.subplots(nrows, ncols, figsize=(11, 3.2 * nrows), squeeze=False)

for ax, model in zip(axes.flat, models_sorted):
    sub = (tier_pivot.loc[model].reindex(DIFFICULTY_ORDER)
           if model in tier_pivot.index.get_level_values("model") else None)
    if sub is None or sub.empty:
        ax.axis("off")
        continue
    sub.plot.bar(ax=ax, ylim=(0, 1), legend=(ax is axes.flat[0]))
    ax.set_title(model, fontsize=9)
    ax.set_xlabel("")
    ax.set_ylabel("pass rate")
    ax.tick_params(axis="x", rotation=0)

# hide any unused subplot slots when the model count doesn't fill the grid
for ax in axes.flat[n:]:
    ax.axis("off")

fig.suptitle("Code-mode vs json_mcp pass rate, by model and difficulty tier", y=1.02)
plt.tight_layout()
plt.show()""")

md("""\
### Where does code-mode's batching advantage actually show up?

Pass rate isn't the only lens -- **turn count** is where batching should \
show up most directly, since code-mode can loop over several tool calls in \
one `execute()` turn while json_mcp needs one turn per call.""")

code("""\
turns_by_tier = (
    clean.groupby(["difficulty", "code_mode"])["model_turns"]
    .mean()
    .unstack("code_mode")
    .rename(columns={True: "code_mode", False: "json_mcp"})
    .reindex(DIFFICULTY_ORDER)
)
display(turns_by_tier)

ax = turns_by_tier.plot.bar(figsize=(9, 4.5))
ax.set_ylabel("avg model turns per episode")
ax.set_title("Average turns by tier: code-mode vs json_mcp")
ax.legend(title="")
plt.tight_layout()
plt.show()""")

md("""\
### Does the tier effect actually come from task pattern, not difficulty?

The difficulty tier and the task's underlying *pattern* are confounded in \
this corpus by construction: the only two templates that require acting on \
a runtime-discovered **set** of records (`update_every_matching_deal`, \
`triage_each_followup`) exist exclusively at the `expert` tier -- every \
`easy`/`medium`/`hard` template is a single-record lookup-and-act, a \
single-query aggregate, or a dependent multi-hop chain, none of which give \
code-mode anything to batch. So "the code-mode gap narrows at expert" (seen \
above) could really mean "the gap narrows on iterate-over-a-set tasks", with \
tier just riding along as a correlated label.

Each episode's own `template`/`pattern` columns (written straight into the \
CSV at run time from the frozen task it ran, not looked up afterward) let \
us check this directly -- including a clean natural control: all four \
`expert`-tier templates share the same nominal difficulty, but only two of \
them are actually iterative, so comparing template-by-template *within* \
`expert` isolates pattern while holding tier fixed.

Writing `template`/`pattern` into the CSV at run time (rather than joining \
against whatever's currently in `frozen/` on disk) matters because the \
corpus gets regenerated over time -- a `task_id` that was `count_open_deals` \
when a CSV was produced can resolve to something else entirely after a \
later regen, so a live join risks silently mislabeling old runs.""")

code("""\
if "template" not in clean.columns:
    raise RuntimeError(
        "this results CSV predates the template/pattern columns -- "
        "re-run the benchmark to get them (see main.py's CSV_FIELDS)."
    )

print("templates per tier:")
display(clean.groupby("difficulty")["template"].unique())""")

code("""\
PATTERN_ORDER = ["single_record_act", "single_query_aggregate", "dependent_chain",
                  "conditional_branch", "iterate_over_set", "parallel_independent"]

pattern_pivot = (
    clean.groupby(["pattern", "code_mode"])["passed"]
    .mean()
    .unstack("code_mode")
    .rename(columns={True: "code_mode", False: "json_mcp"})
    .reindex(PATTERN_ORDER)
)
display(pattern_pivot)

ax = pattern_pivot.plot.bar(figsize=(10, 4.5))
ax.set_ylabel("pass rate")
ax.set_ylim(0, 1)
ax.set_title("Pass rate by task pattern: code-mode vs json_mcp (all models pooled)")
ax.legend(title="")
plt.tight_layout()
plt.show()""")

code("""\
turns_by_pattern = (
    clean.groupby(["pattern", "code_mode"])["model_turns"]
    .mean()
    .unstack("code_mode")
    .rename(columns={True: "code_mode", False: "json_mcp"})
    .reindex(PATTERN_ORDER)
)
display(turns_by_pattern)

ax = turns_by_pattern.plot.bar(figsize=(10, 4.5))
ax.set_ylabel("avg model turns per episode")
ax.set_title("Average turns by task pattern: code-mode vs json_mcp")
ax.legend(title="")
plt.tight_layout()
plt.show()""")

md("""\
### The natural control: template-by-template within `expert` only

All four `expert` templates share the same difficulty label, so this holds \
tier fixed and varies only the pattern -- the cleanest read on whether \
batching itself (not "harder tasks" in general) is what helps.""")

code("""\
expert_only = clean[clean["difficulty"] == "expert"]
EXPERT_TEMPLATE_ORDER = ["decide_by_deal_value", "find_deal_via_chain",
                          "update_every_matching_deal", "triage_each_followup"]

expert_template_pivot = (
    expert_only.groupby(["template", "code_mode"])["passed"]
    .mean()
    .unstack("code_mode")
    .rename(columns={True: "code_mode", False: "json_mcp"})
    .reindex(EXPERT_TEMPLATE_ORDER)
)
display(expert_template_pivot)

ax = expert_template_pivot.plot.bar(figsize=(10, 4.5))
ax.set_ylabel("pass rate")
ax.set_ylim(0, 1)
ax.set_title("Pass rate by expert-tier template: code-mode vs json_mcp\\n(same nominal difficulty, only the last two are iterate-over-set)")
ax.legend(title="")
plt.tight_layout()
plt.show()""")

md("### Pass rate by model and surface (all four surfaces individually)")

code("""\
by_surface = (clean.groupby(["model", "surface"])["passed"].mean()
              .unstack().reindex(columns=SURFACE_ORDER))
display(by_surface)

ax = by_surface.plot.bar(figsize=(11, 5))
ax.set_ylabel("pass rate")
ax.set_ylim(0, 1)
ax.set_title("Pass rate by model and surface")
plt.tight_layout()
plt.show()""")

md("### Efficiency comparison")

code("""\
efficiency = (clean.groupby("model")[
    ["model_turns", "tool_calls_made", "total_tokens", "total_latency_seconds"]
].mean().sort_values("total_tokens"))
display(efficiency)

fig, axes = plt.subplots(1, 2, figsize=(12, 4))
efficiency["model_turns"].plot.barh(ax=axes[0], title="avg model turns per episode")
efficiency["total_tokens"].plot.barh(ax=axes[1], title="avg total tokens per episode")
plt.tight_layout()
plt.show()""")

md("### Error profile across models")

code("""\
error_cols = ["tool_error_count", "syntax_error_count", "type_error_count",
              "runtime_error_count", "parse_error_count"]
error_profile = clean.groupby("model")[error_cols].sum()
display(error_profile)

ax = error_profile.plot.bar(stacked=True, figsize=(11, 5))
ax.set_ylabel("total error count")
ax.set_title("Error profile by model")
plt.tight_layout()
plt.show()""")

md("""\
### Recovery rate

Among episodes that hit at least one error, how often the model still went \
on to pass the task anyway -- evidence the error-feedback loop (showing the \
model its own mistake and letting it try again) is actually working, not \
just padding the turn count.""")

code("""\
had_error = clean[error_cols].sum(axis=1) > 0
recovery = (clean[had_error].groupby("model")["recovered"].mean()
            .rename("recovery_rate_given_error").to_frame())
display(recovery)""")

md("""\
### Harness/infra reliability by model

How often each model's episodes hit a harness-level error (Docker infra, \
model API, or an unexpected episode-level exception) rather than a genuine \
task outcome -- this is about the *serving setup*, not the model's own \
task-solving ability. Computed over every episode (not just clean_run), \
since this is exactly what clean_run excludes elsewhere in this notebook.""")

code("""\
reliability = df.groupby("model")[["infra_error", "model_api_error", "episode_error"]].mean()
display(reliability)

ax = reliability.plot.bar(figsize=(11, 5))
ax.set_ylabel("rate")
ax.set_title("Harness-level error rates by model (not task failures)")
plt.tight_layout()
plt.show()""")

md("""\
## Summary table

One row per model, the headline numbers from everything above, sorted by \
overall pass rate. Also saved to `summary_by_model.csv` alongside this \
notebook.""")

code("""\
summary = pd.DataFrame({
    "overall_pass_rate": overall["pass_rate"],
    "code_mode_pass_rate": code_vs_structured["code_mode (py/js/ts avg)"],
    "json_mcp_pass_rate": code_vs_structured["json_mcp"],
    "avg_turns": efficiency["model_turns"],
    "avg_total_tokens": efficiency["total_tokens"],
    "harness_error_rate": reliability.sum(axis=1),
}).sort_values("overall_pass_rate", ascending=False)
display(summary)

summary.to_csv("summary_by_model.csv")
print("saved to analysis/summary_by_model.csv")""")

notebook = {
    "cells": CELLS,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

out_path = Path(__file__).parent / "benchmark_analysis.ipynb"
out_path.write_text(json.dumps(notebook, indent=1))
print(f"wrote {out_path}")
