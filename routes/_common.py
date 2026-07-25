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
    )


async def sse_response(
    handler: Callable[[StreamBus], Awaitable[None]],
    state: SessionState,
    initial_msg_count: int,
) -> StreamingResponse:
    """统一的 SSE 响应包装器。

    Usage:
        async def my_handler(bus: StreamBus):
            await bus.emit_content("Hello")
            await bus.emit_done()

        return await sse_response(my_handler, state, len(state.messages))
    """
    bus = StreamBus()

    async def event_generator():
        try:
            task = asyncio.create_task(handler(bus))
            async for event in bus.events():
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            await task
        except Exception as e:
            logger.exception("SSE handler error")
            yield f'data: {json.dumps({"type": "content", "text": "出错了，请稍后重试"}, ensure_ascii=False)}\n\n'
        finally:
            try:
                await save_state(state, initial_msg_count)
            except Exception:
                logger.exception("Failed to save state after SSE")
            yield f'data: {json.dumps({"type": "done", "text": ""}, ensure_ascii=False)}\n\n'

    return StreamingResponse(event_generator(), media_type="text/event-stream")
