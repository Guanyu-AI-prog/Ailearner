import json
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

from config import config
from agent.schemas import ChatRequest, SessionState
from agent.core import handle_message
from knowledge.retriever import is_knowledge_ready

# 会话持久化配置
SESSIONS_FILE = os.path.join(os.path.dirname(__file__), "sessions.json")
sessions = {}


def load_sessions():
    """从文件加载会话"""
    global sessions
    if os.path.exists(SESSIONS_FILE):
        try:
            with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for sid, sdata in data.items():
                state = SessionState(session_id=sid)
                state.messages = [m for m in sdata.get("messages", [])]
                state.evaluation_answers = sdata.get("evaluation_answers", {})
                state.evaluation_phase = sdata.get("evaluation_phase", 0)
                state.evaluation_started = sdata.get("evaluation_started", False)
                state.evaluation_done = sdata.get("evaluation_done", False)
                state.evaluation_report = sdata.get("evaluation_report", "")
                state.evaluation_path = sdata.get("evaluation_path", "")
                sessions[sid] = state
            print(f"? 已加载 {len(sessions)} 个会话")
        except Exception as e:
            print(f"? 加载会话失败: {e}")
            sessions = {}


def save_sessions():
    """保存会话到文件"""
    try:
        data = {}
        for sid, state in sessions.items():
            data[sid] = {
                "messages": [m.dict() if hasattr(m, 'dict') else m for m in state.messages],
                "evaluation_answers": state.evaluation_answers,
                "evaluation_phase": state.evaluation_phase,
                "evaluation_started": state.evaluation_started,
                "evaluation_done": state.evaluation_done,
                "evaluation_report": state.evaluation_report,
                "evaluation_path": state.evaluation_path,
            }
        with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"? 保存会话失败: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("? AI 学习引路人 启动中...")
    print(f"? 知识库目录: {config.KNOWLEDGE_DIR}")
    if not config.LLM_API_KEY:
        print("? 警告: 未设置 LLM_API_KEY，请在 .env 中配置")
    else:
        print(f"? LLM 模型: {config.LLM_MODEL}")
    ready = is_knowledge_ready()
    print(f"? 知识库状态: {'已就绪' if ready else '首次启动，正在初始化...'}")
    load_sessions()
    yield
    save_sessions()
    print("? AI 学习引路人 已停止")


app = FastAPI(title="AI 学习引路人", lifespan=lifespan)

templates = Jinja2Templates(directory="web/templates")
app.mount("/static", StaticFiles(directory="web/static"), name="static")


def get_or_create_session(session_id: str) -> SessionState:
    if session_id not in sessions:
        sessions[session_id] = SessionState(session_id=session_id)
    return sessions[session_id]


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
            async for chunk in handle_message(state, request.message, stream=True):
                if chunk["type"] == "content":
                    yield {"data": json.dumps({"type": "content", "text": chunk["text"]}, ensure_ascii=False)}
                elif chunk["type"] == "status":
                    yield {"data": json.dumps({"type": "status", "text": chunk["text"]}, ensure_ascii=False)}
        except Exception as e:
            err_msg = f"出错了：{str(e)}。请检查 LLM API 配置是否正确。"
            yield {"data": json.dumps({"type": "content", "text": err_msg}, ensure_ascii=False)}
        yield {"data": json.dumps({"type": "done", "text": ""}, ensure_ascii=False)}
        save_sessions()

    return EventSourceResponse(event_generator())


@app.get("/api/session/{session_id}/state")
async def get_session_state(session_id: str):
    state = get_or_create_session(session_id)
    return {
        "session_id": state.session_id,
        "evaluation_done": state.evaluation_done,
        "evaluation_started": state.evaluation_started,
        "evaluation_phase": state.evaluation_phase,
        "evaluation_report": state.evaluation_report[:200] + "..." if len(state.evaluation_report) > 200 else state.evaluation_report,
    }


@app.post("/api/session/{session_id}/reset")
async def reset_session(session_id: str):
    if session_id in sessions:
        del sessions[session_id]
        save_sessions()
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.APP_HOST, port=config.APP_PORT)
