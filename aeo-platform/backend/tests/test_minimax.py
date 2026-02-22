"""Test script for LLM providers (MiniMax + GLM5).

Usage:
    python -m pytest tests/test_minimax.py -v
    # Or run directly:
    python tests/test_minimax.py
"""

import json
import os
from typing import Any

import pytest

import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.llm import get_llm_model, LLMResponse, ThinkingBlock, ToolCallBlock
from app.core.llm.minimax import MiniMaxConfig, MiniMaxModel
from app.core.llm.glm5 import GLM5Config, GLM5Model


# Test configuration
TEST_MINIMAX_API_KEY = os.getenv(
    "MINIMAX_API_KEY",
    "sk-api-5cJeRJuKbXPyAmE0DY8OFcQdT0rhWiaLr0LfTM76BrKOmpaRLW4P56lyxlKOv676iO2aVazmH-rocz2S-ZqTa-CAxOXrojPmodmLpshuvvsYNc6-BZL8_1Y",
)
TEST_GLM5_API_KEY = os.getenv("GLM5_API_KEY", "")


@pytest.fixture
def weather_tools() -> list[dict[str, Any]]:
    """Sample weather tool definition."""
    return [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather of a location.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "The city, e.g. San Francisco",
                        }
                    },
                    "required": ["location"],
                },
            },
        }
    ]


# ============================================================================
# Unit tests (no API key needed)
# ============================================================================


class TestLLMResponse:
    """Test LLMResponse and related types."""

    def test_response_to_dict(self):
        response = LLMResponse(
            content="Test content",
            thinking_blocks=[ThinkingBlock(text="Thinking...")],
            tool_calls=[ToolCallBlock(name="test", arguments={"arg": "value"})],
        )
        data = response.to_dict()
        assert data["content"] == "Test content"
        assert len(data["thinking"]) == 1
        assert len(data["tool_calls"]) == 1

    def test_llm_response_type(self):
        assert LLMResponse is not None


class TestMiniMaxConfig:
    """Test MiniMax configuration."""

    def test_config_validation(self):
        config = MiniMaxConfig(api_key="test-key", temperature=0.5, max_tokens=1000)
        config.validate()
        assert config.api_key == "test-key"
        assert config.temperature == 0.5

    def test_config_validation_missing_api_key(self):
        config = MiniMaxConfig(api_key=None)
        with pytest.raises(ValueError, match="API key is required"):
            config.validate()

    def test_config_validation_invalid_temperature(self):
        config = MiniMaxConfig(api_key="test-key", temperature=1.5)
        with pytest.raises(ValueError, match="Temperature must be in range"):
            config.validate()

    def test_config_to_openai_kwargs(self):
        config = MiniMaxConfig(
            api_key="test-key",
            base_url="https://api.minimaxi.com/v1",
            timeout=30.0,
        )
        kwargs = config.to_openai_kwargs()
        assert kwargs["api_key"] == "test-key"
        assert kwargs["base_url"] == "https://api.minimaxi.com/v1"
        assert kwargs["timeout"] == 30.0

    def test_config_to_completion_kwargs(self):
        config = MiniMaxConfig(
            api_key="test-key",
            model_name="MiniMax-M2.1",
            reasoning_split=True,
            temperature=0.8,
            max_tokens=2048,
        )
        kwargs = config.to_completion_kwargs()
        assert kwargs["model"] == "MiniMax-M2.1"
        assert kwargs["temperature"] == 0.8
        assert kwargs["max_tokens"] == 2048
        assert kwargs["extra_body"]["reasoning_split"] is True


class TestGLM5Config:
    """Test GLM5 configuration."""

    def test_config_validation(self):
        config = GLM5Config(api_key="test-key", temperature=0.7)
        config.validate()
        assert config.api_key == "test-key"

    def test_config_validation_missing_api_key(self):
        config = GLM5Config(api_key=None)
        with pytest.raises(ValueError, match="GLM5 API key is required"):
            config.validate()

    def test_config_temperature_range(self):
        # GLM5 allows [0, 2.0]
        config = GLM5Config(api_key="test-key", temperature=1.5)
        config.validate()  # should not raise

        config2 = GLM5Config(api_key="test-key", temperature=2.5)
        with pytest.raises(ValueError, match="Temperature must be in range"):
            config2.validate()

    def test_config_to_completion_kwargs_with_thinking(self):
        config = GLM5Config(
            api_key="test-key",
            model_name="glm-5",
            thinking_enabled=True,
            temperature=0.7,
        )
        kwargs = config.to_completion_kwargs()
        assert kwargs["model"] == "glm-5"
        assert kwargs["extra_body"]["thinking"]["type"] == "enabled"

    def test_config_to_completion_kwargs_without_thinking(self):
        config = GLM5Config(
            api_key="test-key",
            thinking_enabled=False,
        )
        kwargs = config.to_completion_kwargs()
        assert "extra_body" not in kwargs


class TestFactory:
    """Test get_llm_model factory."""

    def test_factory_returns_model(self):
        model = get_llm_model()
        from app.core.llm.base import BaseLLMModel
        assert isinstance(model, BaseLLMModel)


# ============================================================================
# MiniMax API tests (require MINIMAX_API_KEY)
# ============================================================================


@pytest.fixture
def minimax_model() -> MiniMaxModel:
    config = MiniMaxConfig(
        api_key=TEST_MINIMAX_API_KEY,
        model_name="MiniMax-M2.1",
        reasoning_split=True,
        temperature=1.0,
        max_tokens=4096,
    )
    return MiniMaxModel(config)


class TestMiniMaxModel:
    """Test MiniMax model (requires API key)."""

    @pytest.mark.skipif(
        not TEST_MINIMAX_API_KEY or TEST_MINIMAX_API_KEY == "your-api-key",
        reason="No valid MiniMax API key",
    )
    def test_simple_chat(self, minimax_model):
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say 'Hello from MiniMax!' and nothing else."},
        ]
        response = minimax_model(messages=messages)
        assert isinstance(response, LLMResponse)
        assert len(response.content) > 0

    @pytest.mark.skipif(
        not TEST_MINIMAX_API_KEY or TEST_MINIMAX_API_KEY == "your-api-key",
        reason="No valid MiniMax API key",
    )
    def test_streaming(self, minimax_model):
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Count from 1 to 5."},
        ]
        chunks = list(minimax_model.stream(messages=messages))
        assert len(chunks) > 0
        full_content = "".join(c.content for c in chunks if c.content)
        assert len(full_content) > 0

    @pytest.mark.skipif(
        not TEST_MINIMAX_API_KEY or TEST_MINIMAX_API_KEY == "your-api-key",
        reason="No valid MiniMax API key",
    )
    def test_tool_calling(self, minimax_model, weather_tools):
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What's the weather in San Francisco?"},
        ]
        response = minimax_model(messages=messages, tools=weather_tools)
        assert isinstance(response, LLMResponse)
        if response.tool_calls:
            assert response.tool_calls[0].name == "get_weather"


# ============================================================================
# GLM5 API tests (require GLM5_API_KEY)
# ============================================================================


@pytest.fixture
def glm5_model() -> GLM5Model:
    config = GLM5Config(
        api_key=TEST_GLM5_API_KEY,
        model_name="glm-5",
        thinking_enabled=True,
        temperature=0.7,
        max_tokens=4096,
    )
    return GLM5Model(config)


class TestGLM5Model:
    """Test GLM5 model (requires API key)."""

    @pytest.mark.skipif(not TEST_GLM5_API_KEY, reason="No GLM5 API key")
    def test_simple_chat(self, glm5_model):
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say 'Hello from GLM5!' and nothing else."},
        ]
        response = glm5_model(messages=messages)
        assert isinstance(response, LLMResponse)
        assert len(response.content) > 0
        print(f"\nGLM5 Response: {response.content}")

    @pytest.mark.skipif(not TEST_GLM5_API_KEY, reason="No GLM5 API key")
    def test_thinking_content(self, glm5_model):
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is 15 + 27? Explain your thinking."},
        ]
        response = glm5_model(messages=messages)
        assert isinstance(response, LLMResponse)
        assert len(response.content) > 0
        if response.thinking_blocks:
            print(f"\nGLM5 Thinking: {response.thinking_blocks[0].text[:200]}...")

    @pytest.mark.skipif(not TEST_GLM5_API_KEY, reason="No GLM5 API key")
    def test_streaming(self, glm5_model):
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Count from 1 to 5."},
        ]
        chunks = list(glm5_model.stream(messages=messages))
        assert len(chunks) > 0
        full_content = "".join(c.content for c in chunks if c.content)
        assert len(full_content) > 0
        print(f"\nGLM5 Streamed: {full_content}")

    @pytest.mark.skipif(not TEST_GLM5_API_KEY, reason="No GLM5 API key")
    def test_tool_calling(self, glm5_model, weather_tools):
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What's the weather in San Francisco?"},
        ]
        response = glm5_model(messages=messages, tools=weather_tools)
        assert isinstance(response, LLMResponse)
        if response.tool_calls:
            print(f"\nGLM5 Tool call: {response.tool_calls[0].name}")
            assert response.tool_calls[0].name == "get_weather"

    @pytest.mark.skipif(not TEST_GLM5_API_KEY, reason="No GLM5 API key")
    def test_streaming_with_tools(self, glm5_model, weather_tools):
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What's the weather in Beijing?"},
        ]
        chunks = list(glm5_model.stream(messages=messages, tools=weather_tools))
        assert len(chunks) > 0
        # Check if any chunk has tool_calls
        tool_chunks = [c for c in chunks if c.tool_calls]
        if tool_chunks:
            print(f"\nGLM5 Stream tool call: {tool_chunks[0].tool_calls[0].name}")


# ============================================================================
# Manual test runner
# ============================================================================


def run_manual_tests():
    print("=" * 60)
    print("LLM Provider Integration Tests")
    print("=" * 60)

    # Test factory
    print("\n[Test] Factory")
    print("-" * 40)
    model = get_llm_model()
    print(f"Provider: {type(model).__name__}")
    print("OK")

    # Test GLM5 if key available
    if TEST_GLM5_API_KEY:
        print("\n[Test] GLM5 Simple Chat")
        print("-" * 40)
        config = GLM5Config(api_key=TEST_GLM5_API_KEY)
        model = GLM5Model(config)
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say 'Hello from GLM5!' and nothing else."},
        ]
        response = model(messages=messages)
        print(f"Response: {response.content}")

        print("\n[Test] GLM5 Streaming")
        print("-" * 40)
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Count from 1 to 3."},
        ]
        print("Streaming: ", end="", flush=True)
        for chunk in model.stream(messages=messages):
            if chunk.content:
                print(chunk.content, end="", flush=True)
        print("\nOK")
    else:
        print("\nNo GLM5_API_KEY set, skipping GLM5 tests")

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    run_manual_tests()
