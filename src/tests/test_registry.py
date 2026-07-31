from __future__ import annotations

import pytest

from src.llm_clients.registry import ModelConfig, load_model_registry


def test_loads_real_models_yaml():
    configs = load_model_registry("models.yaml")
    # Don't pin an exact count — the fleet is edited freely; just require it
    # parsed a non-trivial set and still contains the anchor models below.
    assert len(configs) >= 3
    names = {c.name for c in configs}
    assert "gemma4-12b-llamacpp-local" in names
    assert "qwen2.5-72b-instruct-q8-llamacpp-local" in names
    assert "qwen3.6-35b-a3b-llamacpp-local" in names


def test_openai_compatible_config_defaults():
    c = ModelConfig(name="x", backend="openai_compatible", model_id="m",
                     base_url="http://localhost:11434/v1")
    assert c.api_key_env is None
    assert c.supports_tool_calling is True


def test_unknown_backend_rejected():
    with pytest.raises(ValueError, match="unknown backend"):
        ModelConfig(name="x", backend="cohere", model_id="m")


def test_openai_compatible_requires_base_url():
    with pytest.raises(ValueError, match="requires base_url"):
        ModelConfig(name="x", backend="openai_compatible", model_id="m")
