import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

from config import config
from agent.schemas import ChatRequest, Message, SessionState
from agent.core import handle_message
from knowledge.retriever import is_knowledge_ready
from db import init_db, get_session, create_session, save_message, update_session, delete_session, close_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("? AI 学习引路人 启动中...")
    print(f"? 知识库目录: {config.KNOWLEDGE_DIR}")
    init_db()
    print("? 数据库已初始化")
    if not config.LLM_API_KEY:
        print("? 警告: 未设置 LLM_API_KEY，请在 .env 中配置")
    else:
        print(f"? LLM 模型: {config.LLM_MODEL}")
    ready = is_knowledge_ready()
    print(f"? 知识库状态: {'已就绪' if ready else '首次启动，正在初始化...'}")
    yield
    close_db()
    print("? AI 学习引路人 已停止")


app = FastAPI(title="AI 学习引路人", lifespan=lifespan)

templates = Jinja2Templates(directory="web/templates")
app.mount("/static", StaticFiles(directory="web/static"), name="static")


def get_or_create_session(session_id: str) -> SessionState:
    data = get_session(session_id)
    if data:
        state = SessionState(session_id=session_id)
        state.messages = [Message(**m) for m in data["messages"]]
        state.evaluation_answers = data["evaluation_answers"]
        state.evaluation_phase = data["evaluation_phase"]
        state.evaluation_started = data["evaluation_started"]
        state.evaluation_done = data["evaluation_done"]
        state.evaluation_report = data["evaluation_report"]
        state.evaluation_path = data["evaluation_path"]
        return state
    create_session(session_id)
    return SessionState(session_id=session_id)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})


@app.post("/api/chat")
async def chat(request: ChatRequest):
    state = get_or_create_session(request.session_id)

    async def event_generator():
        try:
            initial_count = len(state.messages)
            async for chunk in handle_message(state, request.message, stream=True):
                if chunk["type"] == "content":
                    yield {"data": json.dumps({"type": "content", "text": chunk["text"]}, ensure_ascii=False)}
                elif chunk["type"] == "status":
                    yield {"data": json.dumps({"type": "status", "text": chunk["text"]}, ensure_ascii=False)}
        except Exception as e:
            err_msg = f"出错了：{str(e)}。请检查 LLM API 配置是否正确。"
            yield {"data": json.dumps({"type": "content", "text": err_msg}, ensure_ascii=False)}
        finally:
            for m in state.messages[initial_count:]:
                save_message(state.session_id, m.role, m.content)
            update_session(
                state.session_id,
                evaluation_started=state.evaluation_started,
                evaluation_done=state.evaluation_done,
                evaluation_phase=state.evaluation_phase,
                evaluation_report=state.evaluation_report,
                evaluation_path=state.evaluation_path,
                evaluation_answers=state.evaluation_answers,
            )
        yield {"data": json.dumps({"type": "done", "text": ""}, ensure_ascii=False)}

    return EventSourceResponse(event_generator())


@app.get("/api/session/{session_id}/state")
async def get_session_state(session_id: str):
    data = get_session(session_id)
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
    delete_session(session_id)
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.APP_HOST, port=config.APP_PORT)
