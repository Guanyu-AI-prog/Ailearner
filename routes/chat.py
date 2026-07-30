"""聊天路由：普通对话 + SSE 输出。"""

import json
import logging
import time
from collections import OrderedDict

from fastapi import APIRouter

from agent.schemas import ChatRequest
from agent.stream_bus import StreamBus
from agent.orchestrator import handle_message
from db import get_or_create_session
from routes._common import sse_response

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

_rate_limits: OrderedDict = OrderedDict()
_RATE_WINDOW = 60
_RATE_MAX = 20
_last_cleanup = 0.0


def _check_rate_limit(session_id: str) -> bool:
    global _last_cleanup
    now = time.time()

    if now - _last_cleanup > 300:
        _last_cleanup = now
        expired = [k for k, v in _rate_limits.items() if now - v[-1] > _RATE_WINDOW]
        for k in expired:
            del _rate_limits[k]

    timestamps = _rate_limits.get(session_id)
    if timestamps is None:
        timestamps = []
        _rate_limits[session_id] = timestamps
    else:
        while timestamps and now - timestamps[0] >= _RATE_WINDOW:
            timestamps.pop(0)

    if len(timestamps) >= _RATE_MAX:
        return False
    timestamps.append(now)
    _rate_limits.move_to_end(session_id)
    return True


@router.post("/api/chat")
async def chat(request: ChatRequest):
    if not _check_rate_limit(request.session_id):
        async def rate_limited_handler(bus: StreamBus):
            await bus.emit_content("请求太频繁，请稍后再试。")
            await bus.emit_done()

        state = await get_or_create_session(request.session_id)
        return await sse_response(rate_limited_handler, state, len(state.messages))

    state = await get_or_create_session(request.session_id)

    async def handler(bus: StreamBus):
        async for chunk in handle_message(state, request.message, stream=True):
            if chunk["type"] in ("content", "status"):
                await bus.emit(chunk["type"], {"text": chunk["text"]})
        await bus.emit_done()

    return await sse_response(handler, state, len(state.messages))
