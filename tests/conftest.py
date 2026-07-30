"""共享 fixtures：临时数据库、Mock LLM、测试客户端。"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_mock_client(response_text: str = "测试回复"):
    """创建一个 Mock OpenAI 客户端，返回指定文本。"""
    mock_client = MagicMock()

    # 构建 mock response
    mock_choice = MagicMock()
    mock_choice.message.content = response_text
    mock_choice.message.tool_calls = None
    mock_choice.delta.content = response_text
    mock_choice.delta.tool_calls = None

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    # 非流式调用
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    # 流式调用 — 返回 async generator
    async def _fake_stream(**kwargs):
        yield mock_response

    mock_client.chat.completions.create.side_effect = None

    # 通过 side_effect 区分流式/非流式
    _original_create = mock_client.chat.completions.create

    async def _smart_create(**kwargs):
        if kwargs.get("stream"):
            return _fake_stream(**kwargs)
        return mock_response

    mock_client.chat.completions.create = AsyncMock(side_effect=_smart_create)

    return mock_client


@pytest.fixture
def mock_llm(monkeypatch):
    """Mock LLM 客户端，让 agent.llm_client.get_client() 返回 mock。"""
    mock_client = _make_mock_client("你好！我是 AI 学习引路人，有什么可以帮你的？")

    import agent.llm_client
    monkeypatch.setattr(agent.llm_client, "get_client", lambda: mock_client)
    return mock_client


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """临时数据库，测试后自动清理。"""
    import db
    old_path = db.DB_PATH
    db.DB_PATH = tmp_path / "test.db"
    # 重置全局连接，强制重新连接到临时数据库
    db._conn = None
    yield db.DB_PATH
    # 清理：关闭连接，恢复路径
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 在 async 上下文中，由 app 的 lifespan 处理关闭
            pass
        else:
            loop.run_until_complete(db.close_db())
    except Exception:
        pass
    db._conn = None
    db.DB_PATH = old_path


@pytest.fixture
def mock_knowledge(monkeypatch):
    """Mock 知识库检索，返回空结果（不需要真实知识库文件）。"""
    import knowledge.retriever
    monkeypatch.setattr(knowledge.retriever, "retrieve_knowledge", lambda q, n_results=3: [])
    monkeypatch.setattr(knowledge.retriever, "is_knowledge_ready", lambda: True)


@pytest.fixture
async def app_client(tmp_db, mock_llm, mock_knowledge):
    """异步测试客户端，包含完整的 app 初始化。"""
    import httpx
    from main import app
    from db import init_db

    # 手动初始化数据库（ASGITransport 不自动触发 lifespan）
    await init_db()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        timeout=30.0,
    ) as client:
        yield client


def parse_sse_events(response_text: str) -> list:
    """解析 SSE 响应文本为事件列表。"""
    events = []
    for line in response_text.strip().split("\n"):
        line = line.strip()
        if line.startswith("data:"):
            data_str = line[5:].strip()
            if data_str:
                try:
                    events.append(json.loads(data_str))
                except json.JSONDecodeError:
                    events.append({"raw": data_str})
    return events
