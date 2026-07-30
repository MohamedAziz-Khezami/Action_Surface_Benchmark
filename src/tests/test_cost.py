# test_cost.py — cost is the dependent variable of the code-vs-MCP question,
# so its arithmetic and its handling of unpriced models are pinned here.
from __future__ import annotations

from src.meter.meter import EpisodeMeter

_VERIFY_OK = {"passed": True, "reasons": [], "checks": {"answer": True},
              "unauthorized_write_count": 0}


def _meter(price_in=None, price_out=None, sandbox=0.0):
    m = EpisodeMeter("e", "m", "python", "tool_call", "t", "easy", 1, 3, "tpl", "pat",
                     price_in_per_mtok=price_in, price_out_per_mtok=price_out,
                     sandbox_usd_per_second=sandbox)
    return m


def test_token_cost_is_per_million():
    m = _meter(price_in=3.0, price_out=15.0)
    m.record_model_turn(0.0, 1_000_000, 1_000_000)
    row = m.finalize(_VERIFY_OK)
    assert row["input_cost_usd"] == 3.0
    assert row["output_cost_usd"] == 15.0
    assert row["token_cost_usd"] == 18.0


def test_sandbox_cost_is_priced_even_when_tokens_are_not():
    """Code-mode moves cost into compute; that term must never vanish just
    because a local model has no token price."""
    m = _meter(sandbox=0.01)
    m.record_model_turn(0.0, 500, 500)
    m.execution_latency_seconds = 4.0
    row = m.finalize(_VERIFY_OK)
    assert row["cost_priced"] == 0
    assert row["sandbox_cost_usd"] == 0.04
    assert row["episode_cost_usd"] is None       # blank, not a misleading $0
    assert row["token_cost_usd"] is None


def test_episode_cost_sums_tokens_and_sandbox():
    m = _meter(price_in=2.0, price_out=10.0, sandbox=0.001)
    m.record_model_turn(0.0, 100_000, 20_000)    # 0.2 + 0.2 = 0.4 token cost
    m.execution_latency_seconds = 5.0            # 0.005 sandbox
    row = m.finalize(_VERIFY_OK)
    assert abs(row["episode_cost_usd"] - 0.405) < 1e-12


def test_half_priced_model_is_treated_as_unpriced():
    """A price for only one of input/output cannot yield a trustworthy total."""
    m = _meter(price_in=3.0, price_out=None)
    m.record_model_turn(0.0, 1000, 1000)
    row = m.finalize(_VERIFY_OK)
    assert row["cost_priced"] == 0
    assert row["episode_cost_usd"] is None


def test_registry_reads_pricing_fields():
    import tempfile
    import textwrap

    from src.llm_clients.registry import load_model_registry

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(textwrap.dedent("""
            models:
              - name: priced
                backend: openai_compatible
                model_id: x
                base_url: "http://x"
                price_in_per_mtok: 3.0
                price_out_per_mtok: 15.0
              - name: local
                backend: openai_compatible
                model_id: y
                base_url: "http://y"
        """))
        path = f.name
    by_name = {c.name: c for c in load_model_registry(path)}
    assert by_name["priced"].price_in_per_mtok == 3.0
    assert by_name["priced"].price_out_per_mtok == 15.0
    assert by_name["local"].price_in_per_mtok is None
