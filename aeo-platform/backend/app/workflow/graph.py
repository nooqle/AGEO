"""LangGraph workflow builder for Specta AI.

Star topology: orchestrator ←→ agent nodes ←→ orchestrator.
The orchestrator uses LLM Function Calling to dynamically route to agents.
"""

import logging
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from app.workflow.state import AgentState
from app.workflow.orchestrator_node import orchestrator_node, wait_for_user_node
from app.workflow.nodes import a1_brand_node, a2_persona_node
from app.workflow.nodes_a3 import a3_question_node
from app.workflow.nodes_a4 import a4_fetch_node
from app.workflow.nodes_amway import (
    amway_analysis_node,
    amway_content_node,
    amway_extract_node,
    amway_projection_node,
)
from app.workflow.nodes_a5 import a5_analytics_node
from app.workflow.nodes_retired import retired_confidence_executor_node
from app.workflow.nodes_site_confidence import site_confidence_assessment_executor_node
from app.workflow.nodes_table_intake import table_intake_node
from app.workflow.nodes_table_import_apply import table_import_apply_node
from app.workflow.nodes_followup import (
    post_analysis_executor_node,
    drill_down_node,
    compare_snapshots_node,
)
from app.workflow.nodes_knowledge import (
    knowledge_aggregate_node,
    knowledge_compare_node,
    knowledge_export_node,
    knowledge_lookup_node,
)
from app.workflow.nodes_monitoring import create_monitoring_node

logger = logging.getLogger(__name__)

# Global singletons
_compiled_workflow = None
_checkpointer = None
_checkpointer_ctx = None  # async context manager reference for cleanup


def build_workflow() -> StateGraph:
    """Build the Specta AI workflow graph with star topology.

    Topology:
        START → orchestrator ←→ a1_brand
                             ←→ a2_persona
                             ←→ a3_question
                             ←→ a4_fetch
                             ←→ a5_analytics
                             ←→ wait_for_user → END
                             → END

    The orchestrator uses Command(goto=...) for dynamic routing.
    Each agent node returns to orchestrator after execution.
    """
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("a1_brand", a1_brand_node)
    workflow.add_node("a2_persona", a2_persona_node)
    workflow.add_node("a3_question", a3_question_node)
    workflow.add_node("a4_fetch", a4_fetch_node)
    # 3b-1.2：amway 实体抽取/圈层图谱独立节点（拓扑可调度，见 nodes_amway）
    workflow.add_node("amway_extract", amway_extract_node)
    workflow.add_node("amway_projection", amway_projection_node)
    # 3b-1.5: canvas custom nodes (analysis / content) true executors
    workflow.add_node("amway_analysis", amway_analysis_node)
    workflow.add_node("amway_content", amway_content_node)
    workflow.add_node("a5_analytics", a5_analytics_node)
    workflow.add_node(
        "confidence_analysis_executor",
        retired_confidence_executor_node,
    )
    workflow.add_node(
        "site_confidence_assessment_executor",
        site_confidence_assessment_executor_node,
    )
    workflow.add_node("a7_confidence_signal", retired_confidence_executor_node)
    workflow.add_node("table_intake", table_intake_node)
    workflow.add_node("table_import_apply", table_import_apply_node)
    workflow.add_node("wait_for_user", wait_for_user_node)
    workflow.add_node("knowledge_lookup", knowledge_lookup_node)
    workflow.add_node("knowledge_aggregate", knowledge_aggregate_node)
    workflow.add_node("knowledge_compare", knowledge_compare_node)
    workflow.add_node("knowledge_export", knowledge_export_node)
    workflow.add_node("post_analysis_executor", post_analysis_executor_node)

    # Follow-up nodes (Cycle 3, Module 2)
    workflow.add_node("drill_down", drill_down_node)
    workflow.add_node("compare_snapshots", compare_snapshots_node)

    # Monitoring node (Cycle 4)
    workflow.add_node("create_monitoring", create_monitoring_node)

    # Entry point
    workflow.add_edge(START, "orchestrator")

    # Each agent returns to orchestrator after execution
    for node in [
        "a1_brand",
        "a2_persona",
        "a3_question",
        "a4_fetch",
        "amway_extract",
        "amway_projection",
        "amway_analysis",
        "amway_content",
        "a5_analytics",
        "site_confidence_assessment_executor",
        "table_intake",
        "table_import_apply",
        "post_analysis_executor",
    ]:
        workflow.add_edge(node, "orchestrator")

    # Follow-up nodes and monitoring node return to orchestrator
    for node in [
        "drill_down",
        "compare_snapshots",
        "create_monitoring",
        "knowledge_lookup",
        "knowledge_aggregate",
        "knowledge_compare",
        "knowledge_export",
    ]:
        workflow.add_edge(node, "orchestrator")

    # wait_for_user terminates the workflow run (user will re-invoke)
    workflow.add_edge("wait_for_user", END)

    return workflow


async def init_checkpointer() -> None:
    """初始化 PostgreSQL checkpointer。在 app startup 时调用一次。

    如果 DATABASE_URL 不是 PostgreSQL（如 SQLite 开发环境），
    自动降级为 MemorySaver，不抛出异常。
    """
    global _compiled_workflow, _checkpointer, _checkpointer_ctx

    from app.core.config import settings

    db_url = str(settings.DATABASE_URL)
    if not db_url.startswith("postgresql"):
        logger.warning(
            "[Checkpointer] DATABASE_URL 不是 PostgreSQL（当前: %s），使用 MemorySaver",
            db_url[:30],
        )
        _fallback_to_memory_saver()
        return

    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        # 将 SQLAlchemy URL 格式转为 psycopg3 格式
        conn_string = (
            db_url.replace("postgresql+asyncpg://", "postgresql://")
            .replace("postgresql+psycopg2://", "postgresql://")
            .replace("postgresql+psycopg://", "postgresql://")
        )

        ctx = AsyncPostgresSaver.from_conn_string(conn_string)
        checkpointer = await ctx.__aenter__()
        # 立即记录，确保 setup() 失败时 cleanup_checkpointer() 也能关闭连接池
        _checkpointer_ctx = ctx
        _checkpointer = checkpointer
        try:
            await checkpointer.setup()  # 建立 LangGraph checkpoint 表（幂等）
        except Exception:
            # setup 失败，关闭已打开的连接池，重置全局引用
            try:
                await _checkpointer_ctx.__aexit__(None, None, None)
            except Exception:
                pass
            _checkpointer_ctx = None
            _checkpointer = None
            raise  # 重新抛出，让外层 except 触发降级

        _compiled_workflow = build_workflow().compile(checkpointer=checkpointer)

        logger.info("[Checkpointer] AsyncPostgresSaver 初始化成功")

    except ImportError:
        logger.error(
            "[Checkpointer] langgraph-checkpoint-postgres 未安装，降级为 MemorySaver"
        )
        _fallback_to_memory_saver()
    except Exception as e:
        logger.error("[Checkpointer] 初始化失败: %s，降级为 MemorySaver", e)
        _fallback_to_memory_saver()


async def cleanup_checkpointer() -> None:
    """清理 checkpointer 连接。在 app shutdown 时调用。"""
    global _checkpointer_ctx, _checkpointer, _compiled_workflow
    if _checkpointer_ctx is not None:
        try:
            await _checkpointer_ctx.__aexit__(None, None, None)
            logger.info("[Checkpointer] 连接已关闭")
        except Exception as e:
            logger.warning("[Checkpointer] 关闭连接时出错: %s", e)
        _checkpointer_ctx = None
    _checkpointer = None
    _compiled_workflow = None


def _fallback_to_memory_saver() -> None:
    """降级到 MemorySaver。"""
    global _checkpointer, _compiled_workflow
    _checkpointer = MemorySaver()
    _compiled_workflow = build_workflow().compile(checkpointer=_checkpointer)
    logger.warning("[Checkpointer] 已降级为 MemorySaver（数据在进程重启后丢失）")


async def get_compiled_workflow():
    """获取已编译的 workflow（单例）。

    注意：正常情况下 init_checkpointer() 在 startup 时已调用。
    若未调用，此处触发降级初始化。
    """
    global _compiled_workflow
    if _compiled_workflow is None:
        logger.warning(
            "[Checkpointer] get_compiled_workflow 在 init 前被调用，触发降级初始化"
        )
        _fallback_to_memory_saver()
    return _compiled_workflow


def reset_compiled_workflow():
    """Reset the compiled workflow (useful for testing)."""
    global _compiled_workflow, _checkpointer, _checkpointer_ctx
    _compiled_workflow = None
    _checkpointer = None
    _checkpointer_ctx = None
