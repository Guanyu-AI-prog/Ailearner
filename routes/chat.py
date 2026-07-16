import json
import logging
import time
from collections import OrderedDict

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from agent.schemas import ChatRequest
from agent.core import handle_message
from db import get_or_create_session

from routes._common import save_state

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
        async def rate_limited():
            yield {"data": json.dumps({"type": "content", "text": "请求太频繁，请稍后再试。"}, ensure_ascii=False)}
            yield {"data": json.dumps({"type": "done", "text": ""}, ensure_ascii=False)}
        return EventSourceResponse(rate_limited())

    state = await get_or_create_session(request.session_id)

    async def event_generator():
        initial_count = len(state.messages)
        try:
            async for chunk in handle_message(state, request.message, stream=True):
                if chunk["type"] == "content":
                    yield {"data": json.dumps({"type": "content", "text": chunk["text"]}, ensure_ascii=False)}
                elif chunk["type"] == "status":
                    yield {"data": json.dumps({"type": "status", "text": chunk["text"]}, ensure_ascii=False)}
        except Exception as e:
            import traceback
            logger.error(f"chat error: {e}\n{traceback.format_exc()}")
            err_msg = f"出错了：{str(e)}。请检查 LLM API 配置是否正确。"
            yield {"data": json.dumps({"type": "content", "text": err_msg}, ensure_ascii=False)}
        await save_state(state, initial_count)
        yield {"data": json.dumps({"type": "done", "text": ""}, ensure_ascii=False)}

    return EventSourceResponse(event_generator())
