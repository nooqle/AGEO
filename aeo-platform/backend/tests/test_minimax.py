"""Test script for LLM providers (MiniMax + GLM5).

Usage:
    python -m pytest tests/test_minimax.py -v
    # Or run directly:
    python tests/test_minimax.py
"""

import os
from types import SimpleNamespace
from typing import Any

import pytest

import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.llm import get_llm_model, LLMResponse, ThinkingBlock, ToolCallBlock
from app.core.llm.minimax import MiniMaxConfig, MiniMaxModel
from app.core.llm.glm5 import GLM5Config, GLM5Model
from app.core.llm.deepseek import DeepSeekConfig, DeepSeekModel
from app.workflow.confirmation import resolve_confirmation_selection
from app.workflow.nodes_a3 import _question_set_confirmation_update


# Test configuration
TEST_MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
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
        # Use empty string to bypass __post_init__ settings fallback (None triggers auto-fill)
        config = MiniMaxConfig(api_key="")
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
        # Use empty string to bypass __post_init__ settings fallback (None triggers auto-fill)
        config = GLM5Config(api_key="")
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

    def test_web_search_tool_is_passed_to_glm5_request(self):
        request_kwargs: dict[str, Any] = {}
        web_search_tool = {
            "type": "web_search",
            "web_search": {"enable": True, "search_engine": "search_std"},
        }

        GLM5Model._apply_tools_to_request(
            request_kwargs,
            [web_search_tool],
            stream=False,
        )

        assert request_kwargs["tools"] == [web_search_tool]
        assert "extra_body" not in request_kwargs

    def test_streaming_function_tools_keep_tool_stream_with_web_search(self):
        request_kwargs: dict[str, Any] = {
            "extra_body": {"thinking": {"type": "enabled"}}
        }
        function_tool = {
            "type": "function",
            "function": {"name": "lookup", "parameters": {"type": "object"}},
        }
        web_search_tool = {
            "type": "web_search",
            "web_search": {"enable": True, "search_engine": "search_std"},
        }

        GLM5Model._apply_tools_to_request(
            request_kwargs,
            [web_search_tool, function_tool],
            stream=True,
        )

        assert request_kwargs["tools"] == [web_search_tool, function_tool]
        assert request_kwargs["extra_body"]["thinking"]["type"] == "enabled"
        assert request_kwargs["extra_body"]["tool_stream"] is True


@pytest.mark.asyncio
async def test_a3_question_confirmation_hands_off_to_a4_fetch_mode(monkeypatch):
    emitted: list[dict[str, Any]] = []

    async def fake_send_confirmation_request(**kwargs: Any) -> None:
        emitted.append(kwargs)

    monkeypatch.setattr(
        "app.workflow.nodes_a3.send_confirmation_request",
        fake_send_confirmation_request,
    )

    result = await _question_set_confirmation_update(
        {"session_id": "session-1", "user_decisions": {}},
        question_set_id="question-set-1",
        monitor_mode="panorama",
        question_count=12,
    )

    option_ids = [item["id"] for item in result["pending_confirmation"]["options"]]
    assert option_ids == ["fast", "full", "regenerate"]
    assert result["pending_confirmation"]["type"] == "fetch_mode_confirmation"
    assert result["pending_confirmation"]["step_id"] == "a3_to_a4_fetch_mode"
    assert result["user_decisions"]["fetch_mode_pending"] is True
    assert emitted[0]["step_name"] == "选择采集模式"
    assert [item["id"] for item in emitted[0]["options"]] == option_ids


def test_fast_fetch_confirmation_resolves_to_answer_fetch_and_clears_a3_pending():
    resolution = resolve_confirmation_selection(
        selection={"optionId": "fast"},
        option_id="fast",
        user_content="快速采集（推荐）",
        user_decisions={"fetch_mode_pending": True},
        state_values={
            "questions": [{"id": "q1", "text": "问题"}],
            "pending_question_set_confirmation": {"step_id": "a3_to_a4_fetch_mode"},
        },
    )

    assert resolution.user_decisions["fetch_mode_confirmed"] is True
    assert resolution.user_decisions["fetch_mode_pending"] is False
    assert resolution.state_updates["fetch_mode"] == "fast"
    assert resolution.state_updates["pending_question_set_confirmation"] is None
    assert resolution.state_updates["next_required_action"]["tool_name"] == "answer_fetch"
    assert resolution.state_updates["next_required_action"]["tool_args"] == {
        "fetch_mode": "fast"
    }


class TestDeepSeekConfig:
    """Test DeepSeek configuration."""

    def test_config_validation(self):
        config = DeepSeekConfig(api_key="test-key", temperature=0.0)
        config.validate()
        assert config.api_key == "test-key"

    def test_config_validation_missing_api_key(self):
        config = DeepSeekConfig(api_key="")
        with pytest.raises(ValueError, match="DeepSeek API key is required"):
            config.validate()

    def test_config_to_completion_kwargs_without_thinking(self):
        config = DeepSeekConfig(
            api_key="test-key",
            model_name="deepseek-v4-flash",
            thinking_enabled=False,
            temperature=0.0,
            max_tokens=1024,
        )
        kwargs = config.to_completion_kwargs()
        assert kwargs["model"] == "deepseek-v4-flash"
        assert kwargs["temperature"] == 0.0
        assert kwargs["extra_body"]["thinking"]["type"] == "disabled"
        assert "reasoning_effort" not in kwargs

    def test_config_to_completion_kwargs_with_thinking(self):
        config = DeepSeekConfig(
            api_key="test-key",
            model_name="deepseek-v4-pro",
            thinking_enabled=True,
            reasoning_effort="high",
        )
        kwargs = config.to_completion_kwargs()
        assert kwargs["model"] == "deepseek-v4-pro"
        assert kwargs["extra_body"]["thinking"]["type"] == "enabled"
        assert kwargs["reasoning_effort"] == "high"
        assert "temperature" not in kwargs


class TestFactory:
    """Test get_llm_model factory."""

    def test_factory_returns_model(self, monkeypatch):
        import app.config as app_config
        import app.core.llm.glm5 as glm5_module

        monkeypatch.setattr(
            app_config,
            "get_settings",
            lambda: SimpleNamespace(LLM_PROVIDER="glm5"),
        )
        monkeypatch.setattr(
            glm5_module,
            "get_settings",
            lambda: SimpleNamespace(
                GLM5_API_KEY="test-key",
                GLM5_BASE_URL="https://open.bigmodel.cn/api/paas/v4",
                GLM5_MODEL_NAME="glm-5",
                GLM5_THINKING_ENABLED=True,
                GLM5_TEMPERATURE=0.7,
                GLM5_MAX_TOKENS=16384,
            ),
        )

        model = get_llm_model()
        from app.core.llm.base import BaseLLMModel
        assert isinstance(model, BaseLLMModel)

    def test_factory_can_route_to_deepseek_explicitly(self, monkeypatch):
        import app.core.llm.deepseek as deepseek_module

        monkeypatch.setattr(
            deepseek_module,
            "get_settings",
            lambda: SimpleNamespace(DEEPSEEK_API_KEY="test-key"),
        )

        model = get_llm_model(
            provider="deepseek",
            model_name="deepseek-v4-flash",
            thinking_enabled=False,
        )

        assert isinstance(model, DeepSeekModel)
        assert model.config.model_name == "deepseek-v4-flash"
        assert model.config.thinking_enabled is False

    def test_browser_agent_uses_glm5_even_when_global_provider_deepseek(
        self,
        monkeypatch,
    ):
        from app.core.fetchers.browser import browser_agent_loop

        monkeypatch.setattr(
            browser_agent_loop,
            "get_settings",
            lambda: SimpleNamespace(
                LLM_PROVIDER="deepseek",
                BROWSER_AGENT_LLM_API_KEY="",
                GLM5_API_KEY="glm-key",
                GLM5_BASE_URL="https://open.bigmodel.cn/api/paas/v4",
                GLM5_MODEL_NAME="glm-5",
                BROWSER_AGENT_LLM_MODEL_NAME="glm-5",
                BROWSER_AGENT_LLM_THINKING_ENABLED=False,
                BROWSER_AGENT_LLM_MAX_TOKENS=384,
            ),
        )

        model = browser_agent_loop._get_browser_agent_llm_model()

        assert isinstance(model, GLM5Model)
        assert model.config.api_key == "glm-key"
        assert model.config.model_name == "glm-5"


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
