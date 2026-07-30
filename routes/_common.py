"""路由模块共享函数：统一 SSE 响应 + 状态持久化。"""

import asyncio
import json
import logging
from typing import Awaitable, Callable

from fastapi.responses import StreamingResponse

from agent.stream_bus import StreamBus
from agent.schemas import SessionState
from db import save_message, update_session

logger = logging.getLogger(__name__)


async def save_state(state: SessionState, initial_count: int):
    """保存会话状态（新消息 + session 字段）。"""
    try:
        for m in state.messages[initial_count:]:
            await save_message(state.session_id, m.role, m.content)
        await update_session(
            state.session_id,
            evaluation_started=state.evaluation_started,
            evaluation_done=state.evaluation_done,
            evaluation_phase=state.evaluation_phase,
            evaluation_report=state.evaluation_report,
            evaluation_path=state.evaluation_path,
            evaluation_answers=state.evaluation_answers,
            evaluation_scores=state.evaluation_scores,
        )
    except Exception:
        logger.exception("Failed to save state")


async def _safe_handler(handler, bus, state):
    """安全执行 handler：无论成功失败都发送 done 信号。"""
    try:
        await handler(bus)
    except Exception:
        logger.exception("Handler error")
    finally:
        # 确保 done 一定被发送，解锁 bus.events() 阻塞
        await bus.emit_done()


async def sse_response(
    handler: Callable[[StreamBus], Awaitable[None]],
    state: SessionState,
    initial_msg_count: int,
) -> StreamingResponse:
    """统一的 SSE 响应包装器。"""
    bus = StreamBus()

    async def event_generator():
        task = asyncio.create_task(_safe_handler(handler, bus, state))
        try:
            async for event in bus.events():
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
        except Exception:
            logger.exception("SSE event generator error")
        finally:
            # 等待 handler 任务完成（最多 3 秒）
            if not task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=3.0)
                except (asyncio.TimeoutError, Exception):
                    task.cancel()
            await save_state(state, initial_msg_count)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
