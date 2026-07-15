import json
import logging
import time
from collections import OrderedDict
from contextlib import asynccontextmanager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

from config import config
from agent.schemas import ChatRequest
from agent.core import handle_message
from knowledge.retriever import is_knowledge_ready
from db import init_db, get_or_create_session, save_message, update_session, delete_session, close_db
from agent.feishu import handle_event as handle_feishu_event

# Sliding window rate limiter: session_id -> deque of timestamps
_rate_limits: OrderedDict = OrderedDict()
_RATE_WINDOW = 60  # seconds
_RATE_MAX = 20     # max requests per window
_last_cleanup = 0.0


def _check_rate_limit(session_id: str) -> bool:
    global _last_cleanup
    now = time.time()

    # Evict stale entries every 5 minutes to prevent unbounded growth
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
        # Slide window: drop timestamps outside the window
        while timestamps and now - timestamps[0] >= _RATE_WINDOW:
            timestamps.pop(0)

    if len(timestamps) >= _RATE_MAX:
        return False
    timestamps.append(now)
    # Move to end for LRU ordering
    _rate_limits.move_to_end(session_id)
    return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("AI 学习引路人 启动中...")
    logger.info(f"知识库目录: {config.KNOWLEDGE_DIR}")
    await init_db()
    logger.info("数据库已初始化")
    if not config.LLM_API_KEY:
        logger.warning("未设置 LLM_API_KEY，请在 .env 中配置")
    else:
        logger.info(f"LLM 模型: {config.LLM_MODEL}")
    ready = is_knowledge_ready()
    logger.info(f"知识库状态: {'已就绪' if ready else '首次启动，正在初始化...'}")
    yield
    await close_db()
    logger.info("AI 学习引路人 已停止")


app = FastAPI(title="AI 学习引路人", lifespan=lifespan)

templates = Jinja2Templates(directory="web/templates")
app.mount("/static", StaticFiles(directory="web/static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})


@app.post("/api/chat")
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
        # Save state ONCE after all chunks are yielded
        await _save_state(state, initial_count)
        yield {"data": json.dumps({"type": "done", "text": ""}, ensure_ascii=False)}

    return EventSourceResponse(event_generator())


async def _save_state(state, initial_count):
    """Save session state to DB."""
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


@app.get("/api/session/{session_id}/state")
async def get_session_state(session_id: str):
    from db import get_session
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


@app.post("/api/session/{session_id}/reset")
async def reset_session(session_id: str):
    await delete_session(session_id)
    _rate_limits.pop(session_id, None)
    return {"status": "ok"}


@app.post("/webhook/feishu")
async def feishu_webhook(request: Request):
    body = await request.json()
    return await handle_feishu_event(body)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.APP_HOST, port=config.APP_PORT)
