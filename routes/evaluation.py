import json
import logging

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from agent.schemas import ChatRequest
from agent.core import handle_message, should_start_evaluation
from db import get_session, get_or_create_session, delete_session, save_message, update_session
from routes.chat import _save_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.post("/start")
async def evaluation_start(request: ChatRequest):
    state = await get_or_create_session(request.session_id)
    if state.evaluation_started:
        return {"session_id": request.session_id, "status": "already_started"}
    state.evaluation_started = True

    async def event_generator():
        async for chunk in handle_message(state, request.message, stream=True):
            if chunk["type"] == "content":
                yield {"data": json.dumps({"type": "content", "text": chunk["text"]}, ensure_ascii=False)}
            elif chunk["type"] == "status":
                yield {"data": json.dumps({"type": "status", "text": chunk["text"]}, ensure_ascii=False)}
        initial_count = 0
        await _save_state(state, initial_count)
        yield {"data": json.dumps({"type": "done", "text": ""}, ensure_ascii=False)}

    return EventSourceResponse(event_generator())


@router.post("/answer")
async def evaluation_answer(request: ChatRequest):
    state = await get_or_create_session(request.session_id)
    if not state.evaluation_started:
        return {"session_id": request.session_id, "status": "not_started"}

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
            logger.error(f"evaluation answer error: {e}\n{traceback.format_exc()}")
            yield {"data": json.dumps({"type": "content", "text": f"出错了：{str(e)}"}, ensure_ascii=False)}
        await _save_state(state, initial_count)
        yield {"data": json.dumps({"type": "done", "text": ""}, ensure_ascii=False)}

    return EventSourceResponse(event_generator())


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
    }
