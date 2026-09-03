import logging
from contextlib import asynccontextmanager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import config
from db import init_db, close_db
from knowledge.retriever import is_knowledge_ready
from agent.feishu import handle_event as handle_feishu_event
from auth import verify_auth


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

@app.middleware("http")
async def no_cache_middleware(request: Request, call_next):
    response = await call_next(request)
    if "text/html" in response.headers.get("content-type", ""):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response

templates = Jinja2Templates(directory="web/templates")
app.mount("/static", StaticFiles(directory="web/static"), name="static")

from routes.chat import router as chat_router
from routes.evaluation import router as evaluation_router
from routes.persona import router as persona_router

from routes.structured_assessment import api_router as structured_api_router, page_router as structured_page_router
app.include_router(chat_router, dependencies=[Depends(verify_auth)])
app.include_router(evaluation_router, dependencies=[Depends(verify_auth)])
app.include_router(persona_router, dependencies=[Depends(verify_auth)])
app.include_router(structured_page_router)
app.include_router(structured_api_router, dependencies=[Depends(verify_auth)])


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    return templates.TemplateResponse(request, "chat.html")


@app.get("/api/session/{session_id}/state", dependencies=[Depends(verify_auth)])
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


@app.post("/api/session/{session_id}/reset", dependencies=[Depends(verify_auth)])
async def reset_session(session_id: str):
    from db import delete_session
    await delete_session(session_id)
    return {"status": "ok"}


@app.post("/webhook/feishu")
async def feishu_webhook(request: Request):
    body = await request.json()
    return await handle_feishu_event(body)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.APP_HOST, port=config.APP_PORT)
