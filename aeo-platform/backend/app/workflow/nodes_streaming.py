"""Streaming LLM utilities for LangGraph workflow.

This module provides streaming LLM calls with real-time TPAOR event emission.
"""

import asyncio
import logging
from time import perf_counter
from typing import Any, AsyncGenerator, Callable, Generator

from app.core.llm import BaseLLMModel, LLMResponse, LLMUsage
from app.workflow.events import send_tpaor_event, send_progress_event, send_thought_event
from app.workflow.prompt_fingerprint import fingerprint_text, fingerprint_tools

_SENTINEL = object()
_STREAM_IDLE_TIMEOUT_SECONDS = 120
logger = logging.getLogger(__name__)


def _queue_put_threadsafe(
    loop: asyncio.AbstractEventLoop,
    queue: asyncio.Queue[Any],
    item: Any,
) -> bool:
    """Schedule queue delivery from a worker thread without blocking on backpressure."""

    try:
        loop.call_soon_threadsafe(queue.put_nowait, item)
        return True
    except RuntimeError:
        logger.warning("[nodes_streaming] Event loop closed before stream item delivery")
        return False


async def async_wrap_sync_gen(
    gen_factory: Callable[[], Generator[LLMResponse, None, None]],
) -> AsyncGenerator[LLMResponse, None]:
    """Wrap a synchronous generator in a thread so it doesn't block the event loop.

    Uses asyncio.Queue to shuttle chunks from a background thread to the async consumer.
    """
    queue: asyncio.Queue[Any] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def _producer():
        produced = 0
        try:
            for item in gen_factory():
                produced += 1
                if not _queue_put_threadsafe(loop, queue, item):
                    return
        except Exception as exc:
            logger.warning("[nodes_streaming] Producer raised: %s", exc, exc_info=True)
            _queue_put_threadsafe(loop, queue, exc)
        finally:
            logger.info(
                "[nodes_streaming] Producer finished: produced=%d", produced
            )
            _queue_put_threadsafe(loop, queue, _SENTINEL)

    thread_future = loop.run_in_executor(None, _producer)

    try:
        while True:
            try:
                item = await asyncio.wait_for(
                    queue.get(),
                    timeout=_STREAM_IDLE_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "[nodes_streaming] Stream idle timeout: no data received for %d seconds",
                    _STREAM_IDLE_TIMEOUT_SECONDS,
                )
                raise TimeoutError(
                    "LLM streaming timed out: no data received for "
                    f"{_STREAM_IDLE_TIMEOUT_SECONDS} seconds"
                )
            if item is _SENTINEL:
                break
            if isinstance(item, Exception):
                raise item
            yield item
    finally:
        try:
            await thread_future
        except Exception:
            pass  # producer error already propagated via queue


async def stream_llm_with_tpaor(
    session_id: str,
    model: BaseLLMModel,
    messages: list[dict[str, Any]],
    step: str,
    step_name: str,
    progress_start: float = 0.0,
    progress_end: float = 1.0,
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> AsyncGenerator[LLMResponse, None]:
    """Stream LLM output with real-time TPAOR events.

    This function streams LLM output and sends TPAOR events in real-time:
    - thought: Reasoning/thinking content from the model
    - observation: Raw LLM response content (formerly 'response')

    Args:
        session_id: Session identifier for WebSocket events
        model: MiniMax model instance
        messages: List of conversation messages
        step: Current step ID (A1, A2, etc.)
        step_name: Human-readable step name
        progress_start: Starting progress value
        progress_end: Ending progress value

    Yields:
        MiniMaxResponse chunks with incremental content
    """
    # Send initial progress
    await send_progress_event(
        session_id=session_id,
        step=step,
        step_name=step_name,
        progress=progress_start,
        message=f"正在准备{step_name}...",
        status="running",
    )

    # Start TPAOR thought phase
    await send_tpaor_event(
        session_id=session_id,
        phase="thought",
        content=f"正在分析并思考{step_name}的相关信息...",
        is_complete=False,
    )

    full_content = ""
    full_reasoning = ""
    prev_reasoning_len = 0
    chunk_count = 0
    last_sent_progress = progress_start

    # Build kwargs for model.stream()
    stream_kwargs: dict[str, Any] = {}
    if tools:
        stream_kwargs["tools"] = tools
    if max_tokens is not None:
        stream_kwargs["max_tokens"] = max_tokens
    if temperature is not None:
        stream_kwargs["temperature"] = temperature

    # Stream the LLM output (in thread to avoid blocking event loop)
    async for chunk in async_wrap_sync_gen(
        lambda: model.stream(messages, **stream_kwargs)
    ):
        chunk_count += 1

        # Handle thinking/reasoning content
        if chunk.thinking_blocks:
            for block in chunk.thinking_blocks:
                if block.text:
                    full_reasoning += block.text
                    # Send only the delta (new portion) of reasoning
                    delta = full_reasoning[prev_reasoning_len:]
                    prev_reasoning_len = len(full_reasoning)
                    if delta:
                        await send_thought_event(
                            session_id=session_id,
                            content=delta,
                            is_delta=True,
                            is_complete=False,
                        )

        # Handle response content — do NOT send per-chunk action_log
        # (observation phase was flooding action_log via send_tpaor_event)
        if chunk.content:
            full_content += chunk.content

        # Calculate progress based on chunk count (approximate)
        # Use logarithmic curve for more natural progress: fast at start, slow near end
        ratio = min(chunk_count / 50, 0.95)  # 50 chunks to reach ~95%
        progress = progress_start + (progress_end - progress_start) * ratio
        # Only send when progress increases by at least 5% to avoid flooding
        if progress - last_sent_progress >= 0.05:
            last_sent_progress = progress
            await send_progress_event(
                session_id=session_id,
                step=step,
                step_name=step_name,
                progress=round(progress, 2),
                message=f"正在处理{step_name}...",
                status="running",
            )

        yield chunk

    # Mark phases as complete
    if full_reasoning:
        await send_thought_event(
            session_id=session_id,
            content="",
            is_delta=True,
            is_complete=True,
        )

    # Send observation complete only once (not per-chunk)
    await send_tpaor_event(
        session_id=session_id,
        phase="observation",
        content=f"{step_name}完成",
        is_complete=True,
    )

    # Send final progress
    await send_progress_event(
        session_id=session_id,
        step=step,
        step_name=step_name,
        progress=progress_end,
        message=f"{step_name}内容生成完成",
        status="completed",
    )


async def call_llm_streaming(
    session_id: str,
    model: BaseLLMModel,
    messages: list[dict[str, Any]],
    step: str,
    step_name: str,
    task_id: str | None = None,
    skill_key: str | None = None,
    progress_start: float = 0.0,
    progress_end: float = 1.0,
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> LLMResponse:
    """Call LLM with streaming and return final response.

    This is a convenience function that streams LLM output with TPAOR events
    and returns the final aggregated response.

    Args:
        session_id: Session identifier for WebSocket events
        model: MiniMax model instance
        messages: List of conversation messages
        step: Current step ID (A1, A2, etc.)
        step_name: Human-readable step name
        progress_start: Starting progress value
        progress_end: Ending progress value

    Returns:
        Final MiniMaxResponse with complete content
    """
    full_content = ""
    all_thinking_blocks = []
    all_tool_calls = []
    last_finish_reason: str | None = None
    last_usage = None
    started_at = perf_counter()

    async for chunk in stream_llm_with_tpaor(
        session_id=session_id,
        model=model,
        messages=messages,
        step=step,
        step_name=step_name,
        progress_start=progress_start,
        progress_end=progress_end,
        tools=tools,
        max_tokens=max_tokens,
        temperature=temperature,
    ):
        if chunk.content:
            full_content += chunk.content
        if chunk.thinking_blocks:
            all_thinking_blocks.extend(chunk.thinking_blocks)
        if chunk.tool_calls:
            all_tool_calls.extend(chunk.tool_calls)
        if chunk.finish_reason:
            last_finish_reason = chunk.finish_reason
        if chunk.usage:
            last_usage = chunk.usage

    # A completed provider call without counters is an unknown-usage ledger event.
    last_usage = last_usage or LLMUsage()
    response = LLMResponse(
        content=full_content,
        thinking_blocks=all_thinking_blocks,
        tool_calls=all_tool_calls,
        usage=last_usage,
        finish_reason=last_finish_reason,
        latency_ms=max(int((perf_counter() - started_at) * 1000), 0),
    )

    if last_usage:
        from app.services.llm_usage_service import record_llm_usage_async
        from app.services.llm_usage_service import resolve_llm_model_identity

        system_prompt = next(
            (
                str(message.get("content") or "")
                for message in messages
                if message.get("role") == "system"
            ),
            "",
        )
        runtime_context_size = sum(
            len(str(message.get("content") or ""))
            for message in messages
            if message.get("role") != "system"
        )
        usage_metadata = {
            "streaming": True,
            "message_count": len(messages),
            "tool_count": len(tools or []),
            "tool_surface_hash": fingerprint_tools(tools or []),
            "runtime_context_size": runtime_context_size,
            "model_identity": resolve_llm_model_identity(model),
        }
        if system_prompt:
            usage_metadata.update(
                {
                    "static_prompt_hash": fingerprint_text(system_prompt),
                    "system_prompt_length": len(system_prompt),
                }
            )
        usage_metadata.update(extra_metadata or {})

        await record_llm_usage_async(
            session_id=session_id,
            task_id=task_id,
            skill_key=skill_key,
            step=step,
            step_name=step_name,
            model=model,
            usage=last_usage,
            latency_ms=response.latency_ms,
            extra_metadata=usage_metadata,
        )

    return response
