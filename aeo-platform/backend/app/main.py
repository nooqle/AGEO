"""Main application entry point."""

import sys
import io
import asyncio
import json
import os

# Fix Windows console encoding for Chinese characters
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Fix: uvicorn --reload sets WindowsSelectorEventLoopPolicy on Windows,
# but SelectorEventLoop does NOT support asyncio.create_subprocess_exec().
# Patchright/Playwright needs subprocess to launch the browser driver process.
# We monkey-patch uvicorn's asyncio_setup to prevent it from overriding our policy.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    try:
        import uvicorn.loops.asyncio as _uv_asyncio
        _uv_asyncio.asyncio_setup = lambda use_subprocess=False: None
    except ImportError:
        pass

import logging
from uuid import UUID

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.api.deps import get_user_from_token
from app.core.config import settings
from app.core.database import AsyncSessionLocal, init_db
from app.core.websocket_server import (
    manager,
    handle_artifact_action,
    handle_browser_action_resolution,
    handle_user_message,
    handle_confirmation,
    handle_stop,
    handle_recall,
)
import app.models as models
from app.models.session import Session
from app.services.user_service import UserService
from app.startup_checks import startup_checks

# Configure logging after imports
logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Specta AI API",
    description="Specta AI - 品牌声量智能分析平台",
    version="1.0.0",
)


# Startup event
@app.on_event("startup")
async def on_startup():
    """应用启动时执行的初始化任务"""
    logger.info("应用启动中...")
    if not settings.REDIS_URL:
        worker_hint = (
            os.environ.get("WEB_CONCURRENCY")
            or os.environ.get("UVICORN_WORKERS")
            or "1"
        )
        logger.warning(
            "未配置 REDIS_URL，Runtime 共享协调已降级为单进程语义。"
            "当前建议仅以单 worker 方式运行手动分析链路。"
            f" worker_hint={worker_hint}"
        )

    # 执行启动检查（包括 Playwright 浏览器安装）
    if not startup_checks():
        logger.warning("启动检查未完全通过，但应用将继续运行")
        logger.warning("Browser Agent 功能可能不可用")

    models.__all__
    await init_db()

    try:
        from app.services.skill_registry_service import SkillRegistryService

        async with AsyncSessionLocal() as db:
            await SkillRegistryService(db).ensure_builtin_skills()
        logger.info("Skill registry 内置能力已同步")
    except Exception as skill_err:
        logger.warning(f"Skill registry 初始化失败: {skill_err}")

    # LangGraph checkpointer 初始化
    try:
        from app.workflow.graph import init_checkpointer
        await init_checkpointer()
        logger.info("LangGraph checkpointer 已初始化")
    except Exception as cp_err:
        logger.warning(f"Checkpointer 初始化失败，降级为 MemorySaver: {cp_err}")

    # Cycle 3: Orphan Task Recovery (Review C6/T9)
    try:
        from app.services.task_service import TaskService
        async with AsyncSessionLocal() as db:
            service = TaskService(db)
            # timeout_minutes=0: on process restart ALL running tasks are
            # orphaned — no task from the old process can still be alive.
            recovered = await service.recover_orphan_tasks(timeout_minutes=0)
            if recovered > 0:
                logger.warning(f"启动恢复: 标记 {recovered} 个孤儿任务为失败")
    except Exception as recovery_err:
        logger.warning(f"孤儿任务恢复失败: {recovery_err}")

    # Runtime shared coordinator background listeners
    try:
        from app.services.runtime_coordinator import runtime_coordinator

        await runtime_coordinator.start_background_tasks()
        logger.info("Runtime coordinator 后台监听已启动")
    except Exception as runtime_err:
        logger.warning(f"Runtime coordinator 启动失败: {runtime_err}")

    try:
        from app.services.session_event_publisher import session_event_publisher

        await session_event_publisher.start_background_tasks()
        logger.info("Session event publisher 后台监听已启动")
    except Exception as session_event_err:
        logger.warning(f"Session event publisher 启动失败: {session_event_err}")

    # Cycle 4: Start monitoring scheduler
    try:
        from app.services.scheduler import start_scheduler
        await start_scheduler()
        logger.info("监测调度器已启动")
    except Exception as scheduler_err:
        logger.warning(f"监测调度器启动失败: {scheduler_err}")

    logger.info("应用启动完成")


@app.on_event("shutdown")
async def on_shutdown():
    """应用关闭时执行的清理任务"""
    logger.info("应用关闭中...")
    try:
        from app.services.session_event_publisher import session_event_publisher

        await session_event_publisher.stop_background_tasks()
        logger.info("Session event publisher 后台监听已停止")
    except Exception as e:
        logger.warning(f"Session event publisher 停止失败: {e}")
    try:
        from app.services.runtime_coordinator import runtime_coordinator

        await runtime_coordinator.stop_background_tasks()
        logger.info("Runtime coordinator 后台监听已停止")
    except Exception as e:
        logger.warning(f"Runtime coordinator 停止失败: {e}")
    try:
        from app.services.scheduler import stop_scheduler
        await stop_scheduler()
        logger.info("监测调度器已停止")
    except Exception as e:
        logger.warning(f"监测调度器停止失败: {e}")
    try:
        from app.workflow.graph import cleanup_checkpointer
        await cleanup_checkpointer()
        logger.info("Checkpointer 已清理")
    except Exception as e:
        logger.warning(f"Checkpointer 清理失败: {e}")
    logger.info("应用关闭完成")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routes
app.include_router(api_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/health/scheduler")
async def scheduler_health():
    """Scheduler health check endpoint."""
    from app.services.scheduler import get_scheduler_status
    return get_scheduler_status()


# Test WebSocket Endpoint (for debugging)
@app.websocket("/ws-test")
async def websocket_test_endpoint(websocket: WebSocket):
    """Simple test WebSocket endpoint."""
    logger.info("[WebSocket-Test] Connection request received")
    await websocket.accept()
    logger.info("[WebSocket-Test] Connection accepted")
    await websocket.send_text("Hello from server!")
    await websocket.close()
    logger.info("[WebSocket-Test] Connection closed")


# WebSocket Endpoint
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket connection handler."""
    logger.info("=" * 80)
    logger.info(f"[WebSocket] 🔌 New connection request for session: {session_id}")
    logger.info(f"[WebSocket] 📋 Client host: {websocket.client.host if websocket.client else 'unknown'}")
    logger.info(f"[WebSocket] 📋 Client port: {websocket.client.port if websocket.client else 'unknown'}")
    logger.info(f"[WebSocket] 📋 Headers: {dict(websocket.headers)}")
    logger.info(f"[WebSocket] 📋 Query params: {dict(websocket.query_params)}")

    token = websocket.query_params.get("token")
    logger.info(f"[WebSocket] 🔑 Token received: {'Yes' if token else 'No'}")
    if token:
        logger.info(f"[WebSocket] 🔑 Token value: {token[:10]}..." if len(token) > 10 else f"[WebSocket] 🔑 Token value: {token}")

    # Development mode: Allow connection with dev-token
    is_dev_mode = settings.DEBUG and settings.DEV_MODE_ENABLED
    is_dev_token = token == settings.DEV_TOKEN
    logger.info(f"[WebSocket] 🔧 Dev mode enabled: {is_dev_mode}")
    logger.info(f"[WebSocket] 🔧 Is dev token: {is_dev_token}")

    if not token:
        if is_dev_mode:
            logger.warning("[WebSocket] ⚠️  DEVELOPMENT MODE: No token provided, using dev-token")
            token = settings.DEV_TOKEN
            is_dev_token = True
        else:
            logger.error("[WebSocket] ❌ No token provided and not in dev mode, closing connection")
            await websocket.close(code=1008, reason="Unauthorized")
            return

    logger.info("[WebSocket] ✅ Token validation passed")

    try:
        session_uuid = UUID(session_id)
        logger.info(f"[WebSocket] ✅ Session UUID parsed: {session_uuid}")
    except ValueError as e:
        logger.error(f"[WebSocket] ❌ Invalid session UUID: {session_id}, error: {e}")
        await websocket.close(code=1003, reason="Invalid session")
        return

    logger.info("[WebSocket] 🗄️  Opening database session...")
    async with AsyncSessionLocal() as db:
        # Get or create user
        if is_dev_mode and is_dev_token:
            logger.warning(
                f"[WebSocket] ⚠️  DEVELOPMENT MODE: Using dev user ({settings.DEV_USER_EMAIL})"
            )
            user_service = UserService(db)
            user = await user_service.get_or_create_dev_user(
                email=settings.DEV_USER_EMAIL,
                name=settings.DEV_USER_NAME,
            )
            logger.info(f"[WebSocket] ✅ Dev user retrieved: {user.email} (ID: {user.id})")
        else:
            logger.info("[WebSocket] 🔍 Getting user from token...")
            user = await get_user_from_token(token, db)
            if not user:
                logger.error("[WebSocket] ❌ User not found for token, closing connection")
                await websocket.close(code=1008, reason="Unauthorized")
                return
            logger.info(f"[WebSocket] ✅ User retrieved: {user.email} (ID: {user.id})")

        logger.info("[WebSocket] 🔍 Checking session access...")
        session = await db.get(Session, session_uuid)
        if not session:
            logger.error(f"[WebSocket] ❌ Session not found: {session_uuid}")
            await websocket.close(code=1008, reason="Session not found")
            return

        logger.info(f"[WebSocket] ✅ Session found: {session.id}")
        logger.info(f"[WebSocket] 🔍 Session user_id: {session.user_id}, Current user_id: {user.id}")

        if session.user_id != user.id:
            logger.error("[WebSocket] ❌ Session user mismatch, closing connection")
            await websocket.close(code=1008, reason="Access denied")
            return

        logger.info("[WebSocket] ✅ Session access verified")

    logger.info("[WebSocket] 🤝 Accepting WebSocket connection...")
    await websocket.accept()
    logger.info(f"[WebSocket] ✅ Connection accepted for session: {session_id}")
    logger.info("[WebSocket] 📡 Registering connection with manager...")
    await manager.connect(websocket, session_id)
    logger.info("[WebSocket] ✅ Connection fully established and ready")
    logger.info("=" * 80)

    # Start heartbeat task
    heartbeat_task = asyncio.create_task(
        _websocket_heartbeat(websocket, session_id)
    )

    # Track running agent task so we don't block the WS receive loop
    agent_task: asyncio.Task | None = None

    def _on_agent_done(task: asyncio.Task):
        """Log errors from background agent task and notify frontend."""
        nonlocal agent_task
        agent_task = None
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.error(f"[WebSocket] Agent task error: {exc}")
            # Notify frontend about the unhandled error so it doesn't hang
            asyncio.create_task(
                manager.emit_to_websocket(websocket, "error", {
                    "step": "system",
                    "error": f"任务异常终止: {exc}",
                    "recoverable": True,
                })
            )

    try:
        while True:
            # Receive message with timeout to allow heartbeat checks
            try:
                raw_text = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0  # 30 second timeout for receive
                )
                message = json.loads(raw_text)
            except asyncio.TimeoutError:
                # No message received in 30 seconds, continue to check connection
                continue
            except (json.JSONDecodeError, ValueError):
                logger.warning(f"[WebSocket] Invalid JSON from session: {session_id}")
                continue

            event = message.get("event")
            data = message.get("data", {})

            logger.info(
                f"[WebSocket] Received event: {event} from session: {session_id}"
            )

            # Route to corresponding handler
            # user_message and confirmation run as background tasks
            # so the WS loop stays responsive to pings
            if event == "user_message":
                if agent_task and not agent_task.done():
                    logger.warning("[WebSocket] Agent already running, ignoring message")
                    await manager.emit_to_websocket(websocket, "error", {
                        "message": "正在执行中，请等待当前任务完成",
                        "recoverable": True,
                    })
                else:
                    agent_task = asyncio.create_task(
                        handle_user_message(websocket, session_id, data)
                    )
                    agent_task.add_done_callback(_on_agent_done)
            elif event == "confirmation":
                _running = agent_task  # local ref to avoid race with _on_agent_done
                if _running and not _running.done():
                    # Race condition: agent_task may still be running _save_final_message
                    # after sending inline_confirmation. Wait for it to finish.
                    logger.info("[WebSocket] Agent task still running, waiting for completion before handling confirmation...")
                    try:
                        await asyncio.wait_for(_running, timeout=60)
                    except asyncio.TimeoutError:
                        logger.warning("[WebSocket] Agent task did not complete in 60s, ignoring confirmation")
                        await manager.emit_to_websocket(websocket, "error", {
                            "message": "当前任务未能及时完成，请稍后重试",
                            "recoverable": True,
                        })
                        continue
                agent_task = asyncio.create_task(
                    handle_confirmation(websocket, session_id, data)
                )
                agent_task.add_done_callback(_on_agent_done)
            elif event == "stop":
                if agent_task and not agent_task.done():
                    agent_task.cancel()
                    logger.info(f"[WebSocket] Cancelled agent task for session {session_id}")
                await handle_stop(websocket, session_id)
            elif event == "recall":
                if agent_task and not agent_task.done():
                    await manager.emit_to_websocket(websocket, "error", {
                        "message": "正在执行中，请等待当前任务完成后再回退",
                        "recoverable": True,
                    })
                else:
                    agent_task = asyncio.create_task(
                        handle_recall(websocket, session_id, data)
                    )
                    agent_task.add_done_callback(_on_agent_done)
            elif event == "artifact_action":
                if agent_task and not agent_task.done():
                    await manager.emit_to_websocket(websocket, "error", {
                        "message": "正在执行中，请等待当前任务完成",
                        "recoverable": True,
                    })
                else:
                    agent_task = asyncio.create_task(
                        handle_artifact_action(websocket, session_id, data)
                    )
                    agent_task.add_done_callback(_on_agent_done)
            elif event == "browser_action_resolution":
                await handle_browser_action_resolution(websocket, session_id, data)
            elif event == "ping":
                await manager.emit_to_websocket(websocket, "pong", {})
            else:
                logger.warning(f"[WebSocket] Unknown event: {event}")

    except WebSocketDisconnect:
        logger.info("=" * 80)
        logger.info(f"[WebSocket] 👋 Client disconnected from session: {session_id}")
        logger.info("=" * 80)
    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"[WebSocket] ❌ Error occurred: {e}")
        logger.error(f"[WebSocket] ❌ Error type: {type(e).__name__}")
        import traceback

        traceback.print_exc()
        logger.error("=" * 80)
    finally:
        # Cancel heartbeat task
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        # Let agent task finish naturally so _save_final_message can persist
        # the agent reply to DB. WS send errors are caught by emit functions.
        # Capture a local reference first — _on_agent_done may set agent_task=None
        # concurrently, which would cause AttributeError on .cancel().
        _pending = agent_task
        if _pending and not _pending.done():
            try:
                await asyncio.wait_for(_pending, timeout=30.0)
            except asyncio.TimeoutError:
                logger.warning("[WebSocket] Agent task timed out after disconnect, cancelling")
                _pending.cancel()
                try:
                    await _pending
                except (asyncio.CancelledError, Exception):
                    pass
            except Exception:
                pass
        manager.disconnect(websocket)


async def _websocket_heartbeat(websocket: WebSocket, session_id: str):
    """Send periodic heartbeat to keep connection alive.

    Args:
        websocket: WebSocket connection
        session_id: Session ID
    """
    try:
        while True:
            await asyncio.sleep(20)  # Send heartbeat every 20 seconds
            try:
                await websocket.send_json({"event": "heartbeat", "data": {}})
                logger.debug(f"[WebSocket] Heartbeat sent to session: {session_id}")
            except Exception:
                # Connection is dead, exit heartbeat loop
                logger.warning(f"[WebSocket] Heartbeat failed for session: {session_id}")
                break
    except asyncio.CancelledError:
        logger.debug(f"[WebSocket] Heartbeat cancelled for session: {session_id}")
        raise


# ASGI application entry point
socket_app = app
