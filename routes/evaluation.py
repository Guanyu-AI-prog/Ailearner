"""评估路由：开始评估 + 答题 + 查看报告。"""

import logging

from fastapi import APIRouter

from agent.schemas import ChatRequest
from agent.stream_bus import StreamBus
from agent.orchestrator import handle_message
from db import get_session, get_or_create_session
from routes._common import sse_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.post("/start")
async def evaluation_start(request: ChatRequest):
    state = await get_or_create_session(request.session_id)
    if state.evaluation_started:
        return {"session_id": request.session_id, "status": "already_started"}
    state.evaluation_started = True

    async def handler(bus: StreamBus):
        async for chunk in handle_message(state, request.message, stream=True):
            if chunk["type"] in ("content", "status"):
                await bus.emit(chunk["type"], {"text": chunk["text"]})
        await bus.emit_done()

    return await sse_response(handler, state, 0)


@router.post("/answer")
async def evaluation_answer(request: ChatRequest):
    state = await get_or_create_session(request.session_id)
    if not state.evaluation_started:
        return {"session_id": request.session_id, "status": "not_started"}

    async def handler(bus: StreamBus):
        async for chunk in handle_message(state, request.message, stream=True):
            if chunk["type"] in ("content", "status"):
                await bus.emit(chunk["type"], {"text": chunk["text"]})
        await bus.emit_done()

    return await sse_response(handler, state, len(state.messages))


@router.get("/report/{session_id}")
async def evaluation_report(session_id: str):
    data = await get_session(session_id)
    if not data:
        return {"session_id": session_id, "evaluation_done": False, "evaluation_started": False, "evaluation_phase": 0, "evaluation_report": ""}
    report = data.get("evaluation_report", "")
    return {
        "session_id": session_id,
        "evaluation_done": data["evaluation_done"],
        "evaluation_started": data["evaluation_started"],
        "evaluation_phase": data["evaluation_phase"],
        "evaluation_report": (report[:200] + "...") if len(report) > 200 else report,
        "evaluation_scores": data.get("evaluation_scores", {}),
    }
