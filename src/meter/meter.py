# meter.py — per-episode metrics collection.
from __future__ import annotations

import time

# DomainError codes raised by src/core/errors.py (see impl.py/services.py),
# plus the tool-server envelope's own error codes for a request-validation
# failure or an unexpected exception — both are still "the tool-server said
# something went wrong," the same category as not_found/duplicate_key/etc.
_DOMAIN_ERROR_CODES = {"not_found", "duplicate_key", "malformed_filter", "validation_error", "internal_error"}

# Exception class names
_TRANSPORT_ERROR_NAMES = {"HTTPError", "ConnectionError", "Timeout"}


def _categorize_error(error: dict) -> str:
    """Returns one of 'cap', 'syntax', 'type', 'tool', 'runtime'."""
    code = error.get("code")
    name = error.get("name")
    # Checked first, and kept out of every error bucket: a cap hit is the
    # batching ablation working as designed, not a defect in the model's code.
    # Counting it as a runtime error would make the capped arm look like it
    # degraded code quality when all it did was enforce its own constraint,
    # and would inflate `recovered` for every episode that simply continued
    # in the next block.
    if code == "tool_call_limit_exceeded":
        return "cap"
    if code == "ts_syntax_error":
        return "syntax"
    if code == "ts_type_error":
        return "type"
    if code in _DOMAIN_ERROR_CODES:
        return "tool"
    if name == "SyntaxError":
        return "syntax"
    if name in _TRANSPORT_ERROR_NAMES:
        return "tool"
    return "runtime"


class EpisodeMeter:
    def __init__(self, episode_id: str, model: str, surface: str, interaction_mode: str,
                 task_id: str, difficulty: str, world_seed: int, n_functions_expected: int,
                 template: str, pattern: str,
                 max_tool_calls_per_exec: int | None = None,
                 turn_budget: int | None = None,
                 price_in_per_mtok: float | None = None,
                 price_out_per_mtok: float | None = None,
                 sandbox_usd_per_second: float = 0.0):
        self.episode_id = episode_id
        self.model = model
        # Recorded per episode so a capped run is identifiable from the CSV
        # alone. Without it, the ablation's two arms are indistinguishable in
        # the results and could only be told apart by which file they landed in.
        self.max_tool_calls_per_exec = max_tool_calls_per_exec
        # The budget this episode actually got. It varies per task now, so
        # hit_turn_budget is uninterpretable without it — 20 turns used means
        # something very different under a budget of 20 than under 60.
        self.turn_budget = turn_budget
        # Prices are captured per episode so the cost is reproducible from the
        # CSV even if models.yaml or config.py later change.
        self.price_in_per_mtok = price_in_per_mtok
        self.price_out_per_mtok = price_out_per_mtok
        self.sandbox_usd_per_second = sandbox_usd_per_second
        self.surface = surface
        self.interaction_mode = interaction_mode
        self.task_id = task_id
        self.difficulty = difficulty
        self.world_seed = world_seed
        self.n_functions_expected = n_functions_expected
        self.template = template
        self.pattern = pattern

        self._start = time.monotonic()

        self.model_turns = 0
        self.model_latency_seconds = 0.0
        self.input_tokens = 0
        self.output_tokens = 0

        self.tool_calls_made = 0
        self.execution_latency_seconds = 0.0

        self.tool_error_count = 0
        # Times an execute() block was stopped by max_tool_calls_per_exec.
        # 0 for every uncapped episode, so it is also a check that the cap
        # actually bit rather than being silently unreachable.
        self.exec_cap_hit_count = 0
        self.syntax_error_count = 0
        self.type_error_count = 0
        self.runtime_error_count = 0
        self.parse_error_count = 0

        self.hit_turn_budget = 0
        self.infra_error = 0
        self.model_api_error = 0
        self.model_api_error_message = ""
        # The model emitted an unusable action (ungrammatical tool call, or
        # arguments that are not valid JSON). A FAILED episode, not an
        # infrastructure fault — it keeps its row, gets verified against
        # whatever state it reached, and never trips the circuit breaker.
        self.malformed_action = 0
        self.malformed_action_message = ""
        self.episode_error = 0
        self.episode_error_message = ""

    def record_model_turn(self, latency_seconds: float, input_tokens: int, output_tokens: int) -> None:
        self.model_turns += 1
        self.model_latency_seconds += latency_seconds
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens

    def record_exec_result(self, exec_result: dict, latency_seconds: float) -> None:
        """`exec_result` is one episode.exec() response: {ok, stdout, value,
        error, tool_calls}."""
        self.tool_calls_made += exec_result.get("tool_calls", 0)
        self.execution_latency_seconds += latency_seconds
        error = exec_result.get("error")
        if error:
            bucket = _categorize_error(error)
            if bucket == "cap":
                self.exec_cap_hit_count += 1
            elif bucket == "syntax":
                self.syntax_error_count += 1
            elif bucket == "type":
                self.type_error_count += 1
            elif bucket == "tool":
                self.tool_error_count += 1
            else:
                self.runtime_error_count += 1

    def record_parse_error(self) -> None:
        self.parse_error_count += 1

    def mark_hit_turn_budget(self) -> None:
        self.hit_turn_budget = 1

    def mark_infra_error(self) -> None:
        self.infra_error = 1

    def mark_episode_error(self, message: str) -> None:
        """Anything else inside the turn loop / grading blew up (executor
        container hung, tool-server network blip, a bug in verify() or
        state_diff...) — distinct from model_api_error (the model call
        itself) and infra_error (episode/Docker setup). Last-resort net so
        NOTHING inside run_episode() can crash the batch run in main.py."""
        self.episode_error = 1
        self.episode_error_message = message

    def mark_malformed_action(self, message: str) -> None:
        """Distinct from mark_model_api_error: the server answered, the model
        failed. Recorded per episode so the rate is comparable across surfaces
        — it is expected to be higher for json_mcp, which emits several varied
        structured calls per episode rather than a few fixed execute() ones."""
        self.malformed_action = 1
        self.malformed_action_message = message[:500]

    def mark_model_api_error(self, message: str) -> None:
        """The call to the model itself failed (context-length exceeded,
        rate limit, malformed request, provider outage...) — distinct from
        infra_error (episode/Docker setup) and from the exec-time error
        buckets (the model's own code/tool-call failing). Covers whatever
        the episode's LAST attempted turn was; earlier successful turns are
        still counted via model_turns/tokens."""
        self.model_api_error = 1
        self.model_api_error_message = message

    def finalize(self, verify_result: dict) -> dict:
        """`verify_result` is verify()'s output: {passed, reasons, checks,
        unauthorized_write_count}."""
        total_latency_seconds = time.monotonic() - self._start
        total_tokens = self.input_tokens + self.output_tokens
        checks = verify_result.get("checks", {})
        fulfillment_score = (sum(checks.values()) / len(checks)) if checks else 0.0

        # Blast radius: rows written that the task never authorized. Defaults to
        # 0 on the infra/api/episode-error paths, whose synthetic verify_result
        # has no diff behind it — those episodes never ran the model's writes.
        unauthorized_write_count = verify_result.get("unauthorized_write_count", 0)

        # Cost. Split into token cost and sandbox-compute cost so each is
        # inspectable and the sandbox term (code-mode's hidden cost) is never
        # buried. `cost_priced` is 0 when this model has no token price, so a
        # blank cost is distinguishable from a genuine $0.
        cost_priced = int(self.price_in_per_mtok is not None
                          and self.price_out_per_mtok is not None)
        if cost_priced:
            input_cost_usd = self.input_tokens / 1_000_000 * self.price_in_per_mtok
            output_cost_usd = self.output_tokens / 1_000_000 * self.price_out_per_mtok
            token_cost_usd = input_cost_usd + output_cost_usd
        else:
            input_cost_usd = output_cost_usd = token_cost_usd = None
        sandbox_cost_usd = self.execution_latency_seconds * self.sandbox_usd_per_second
        episode_cost_usd = (token_cost_usd + sandbox_cost_usd) if cost_priced else None

        total_errors = (self.tool_error_count + self.syntax_error_count
                         + self.type_error_count + self.runtime_error_count
                         + self.parse_error_count)
        recovered = 1 if (total_errors > 0 and verify_result["passed"]) else 0

        # answer_correct/db_correct: the coarsest 2-bucket grouping of the six
        # named checks — 'answer' is its own bucket, everything else is 'db'.
        answer_correct = int(checks.get("answer", False))
        db_check_names = [n for n in checks if n != "answer"]
        db_correct = int(all(checks[n] for n in db_check_names)) if db_check_names else 1

        return {
            "episode_id": self.episode_id,
            "model": self.model,
            "surface": self.surface,
            "interaction_mode": self.interaction_mode,
            "task_id": self.task_id,
            "difficulty": self.difficulty,
            "template": self.template,
            "pattern": self.pattern,
            "world_seed": self.world_seed,
            "passed": int(verify_result["passed"]),
            "answer_correct": answer_correct,
            "db_correct": db_correct,
            "fulfillment_score": fulfillment_score,
            "max_tool_calls_per_exec": self.max_tool_calls_per_exec,
            "turn_budget": self.turn_budget,
            "n_functions_expected": self.n_functions_expected,
            "tool_calls_made": self.tool_calls_made,
            "model_turns": self.model_turns,
            "total_latency_seconds": total_latency_seconds,
            "model_latency_seconds": self.model_latency_seconds,
            "execution_latency_seconds": self.execution_latency_seconds,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": total_tokens,
            "cost_priced": cost_priced,
            "input_cost_usd": input_cost_usd,
            "output_cost_usd": output_cost_usd,
            "token_cost_usd": token_cost_usd,
            "sandbox_cost_usd": sandbox_cost_usd,
            "episode_cost_usd": episode_cost_usd,
            "tool_error_count": self.tool_error_count,
            "syntax_error_count": self.syntax_error_count,
            "type_error_count": self.type_error_count,
            "runtime_error_count": self.runtime_error_count,
            "parse_error_count": self.parse_error_count,
            "exec_cap_hit_count": self.exec_cap_hit_count,
            "recovered": recovered,
            "unauthorized_write_count": unauthorized_write_count,
            "had_unauthorized_write": int(unauthorized_write_count > 0),
            "hit_turn_budget": self.hit_turn_budget,
            "infra_error": self.infra_error,
            "model_api_error": self.model_api_error,
            "model_api_error_message": self.model_api_error_message,
            "malformed_action": self.malformed_action,
            "malformed_action_message": self.malformed_action_message,
            "episode_error": self.episode_error,
            "episode_error_message": self.episode_error_message,
            "verifier_reasons": "; ".join(verify_result["reasons"]),
        }
