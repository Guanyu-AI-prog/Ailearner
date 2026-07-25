"""
冒烟测试 — 重构安全网

目标：确保核心流程在重构后仍然正常工作。
覆盖：首页、普通对话、评估全流程、会话持久化、会话重置、限流。
不依赖真实 LLM API，全部 mock。
"""

import json
import pytest
import uuid

from tests.conftest import parse_sse_events


# ─── 首页 ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_index_page(app_client):
    """GET / 返回 200，包含页面标题。"""
    resp = await app_client.get("/")
    assert resp.status_code == 200
    assert "AI" in resp.text or "学习" in resp.text


@pytest.mark.asyncio
async def test_chat_page(app_client):
    """GET /chat 返回 200。"""
    resp = await app_client.get("/chat")
    assert resp.status_code == 200


# ─── 普通对话 ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_returns_sse(app_client, mock_llm):
    """POST /api/chat 返回 SSE 流，包含 content 和 done 事件。"""
    mock_llm.chat.completions.create.side_effect = None

    # 重新设置 mock：流式返回内容
    async def _stream(**kwargs):
        if kwargs.get("stream"):
            async def _gen():
                chunk = MagicMock()
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta.content = "你好！"
                chunk.choices[0].delta.tool_calls = None
                yield chunk
            return _gen()
        # 非流式
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = "你好！"
        resp.choices[0].message.tool_calls = None
        return resp

    from unittest.mock import MagicMock, AsyncMock
    mock_llm.chat.completions.create = AsyncMock(side_effect=_stream)

    resp = await app_client.post(
        "/api/chat",
        json={"session_id": f"smoke-{uuid.uuid4().hex[:8]}", "message": "你好"},
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")

    events = parse_sse_events(resp.text)
    types = [e.get("type") for e in events]
    assert "content" in types, f"应包含 content 事件，实际: {types}"
    assert "done" in types, f"应包含 done 事件，实际: {types}"


# ─── 评估全流程（"用 AI" 路径）──────────────────────────────────────

@pytest.mark.asyncio
async def test_evaluation_use_ai_full_flow(app_client):
    """完整走一遍「用 AI」评估流程：开始 → 选场景 → 答 2 题 → 拿报告。"""
    sid = f"eval-use-{uuid.uuid4().hex[:8]}"

    # Step 1: 触发评估
    resp = await app_client.post(
        "/api/chat",
        json={"session_id": sid, "message": "帮我评估一下"},
    )
    assert resp.status_code == 200
    events = parse_sse_events(resp.text)
    content_texts = [e["text"] for e in events if e.get("type") == "content"]
    full_reply = "".join(content_texts)
    assert "学 AI" in full_reply or "用 AI" in full_reply, f"应包含路径选择，实际: {full_reply[:100]}"

    # Step 2: 选择「用 AI」
    resp = await app_client.post(
        "/api/chat",
        json={"session_id": sid, "message": "2"},
    )
    events = parse_sse_events(resp.text)
    content_texts = [e["text"] for e in events if e.get("type") == "content"]
    full_reply = "".join(content_texts)
    assert "场景" in full_reply or "1." in full_reply, f"应展示场景列表，实际: {full_reply[:100]}"

    # Step 3: 选择场景
    resp = await app_client.post(
        "/api/chat",
        json={"session_id": sid, "message": "1"},
    )
    events = parse_sse_events(resp.text)
    content_texts = [e["text"] for e in events if e.get("type") == "content"]
    full_reply = "".join(content_texts)
    # 应该展示 usage_time 问题
    assert "时间" in full_reply or "AI" in full_reply or "1." in full_reply

    # Step 4: 答 usage_time
    resp = await app_client.post(
        "/api/chat",
        json={"session_id": sid, "message": "2"},
    )
    events = parse_sse_events(resp.text)
    content_texts = [e["text"] for e in events if e.get("type") == "content"]
    full_reply = "".join(content_texts)
    # 应该展示 current_tools 问题
    assert "工具" in full_reply or "1." in full_reply

    # Step 5: 答 current_tools → 拿报告
    resp = await app_client.post(
        "/api/chat",
        json={"session_id": sid, "message": "1"},
    )
    events = parse_sse_events(resp.text)
    content_texts = [e["text"] for e in events if e.get("type") == "content"]
    full_reply = "".join(content_texts)
    assert "评估" in full_reply or "建议" in full_reply or "模板" in full_reply, \
        f"应包含评估报告，实际: {full_reply[:100]}"


# ─── 评估全流程（"学 AI" 路径）──────────────────────────────────────

@pytest.mark.asyncio
async def test_evaluation_learn_ai_full_flow(app_client):
    """完整走一遍「学 AI」评估流程：7 道题 → 拿报告。"""
    sid = f"eval-learn-{uuid.uuid4().hex[:8]}"

    # 触发评估
    resp = await app_client.post("/api/chat", json={"session_id": sid, "message": "评估"})
    assert resp.status_code == 200

    # 选「学 AI」
    resp = await app_client.post("/api/chat", json={"session_id": sid, "message": "1"})
    assert resp.status_code == 200

    # 答 7 道题（LEARN_AI_QUESTIONS）
    answers = ["2", "1", "3", "2", "2", "2", "1"]
    for i, ans in enumerate(answers):
        resp = await app_client.post("/api/chat", json={"session_id": sid, "message": ans})
        assert resp.status_code == 200, f"第 {i+1} 题失败"

    # 最后一次响应应包含报告
    events = parse_sse_events(resp.text)
    content_texts = [e["text"] for e in events if e.get("type") == "content"]
    full_reply = "".join(content_texts)
    assert "评估" in full_reply or "建议" in full_reply or "学习" in full_reply, \
        f"应包含评估报告，实际: {full_reply[:200]}"


# ─── 评估无效输入重试 ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_evaluation_invalid_input_reprompts(app_client):
    """评估中输入无效内容，应重新提示而非崩溃。"""
    sid = f"eval-invalid-{uuid.uuid4().hex[:8]}"

    # 触发评估
    await app_client.post("/api/chat", json={"session_id": sid, "message": "评估"})

    # 选「用 AI」
    await app_client.post("/api/chat", json={"session_id": sid, "message": "2"})

    # 输入无效内容（选场景时）
    resp = await app_client.post("/api/chat", json={"session_id": sid, "message": "xyz"})
    events = parse_sse_events(resp.text)
    content_texts = [e["text"] for e in events if e.get("type") == "content"]
    full_reply = "".join(content_texts)
    assert "没听清" in full_reply or "再发" in full_reply or "输入" in full_reply, \
        f"无效输入应重新提示，实际: {full_reply[:100]}"


# ─── 会话持久化 ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_session_state_persists(app_client, mock_llm):
    """会话状态在请求间持久化：发送消息后重新获取 session，消息应保留。"""
    sid = f"persist-{uuid.uuid4().hex[:8]}"

    # 设置 mock 响应
    from unittest.mock import MagicMock, AsyncMock

    async def _stream(**kwargs):
        if kwargs.get("stream"):
            async def _gen():
                chunk = MagicMock()
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta.content = "收到"
                chunk.choices[0].delta.tool_calls = None
                yield chunk
            return _gen()
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = "收到"
        resp.choices[0].message.tool_calls = None
        return resp

    mock_llm.chat.completions.create = AsyncMock(side_effect=_stream)

    # 发送一条消息
    resp = await app_client.post("/api/chat", json={"session_id": sid, "message": "你好"})
    assert resp.status_code == 200

    # 查询 session 状态
    resp = await app_client.get(f"/api/session/{sid}/state")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == sid
    assert data["evaluation_started"] is False


# ─── 会话重置 ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_session_reset(app_client):
    """POST /api/session/{id}/reset 清除会话数据。"""
    sid = f"reset-{uuid.uuid4().hex[:8]}"

    # 先创建一个会话
    await app_client.post("/api/chat", json={"session_id": sid, "message": "你好"})

    # 重置
    resp = await app_client.post(f"/api/session/{sid}/reset")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # 验证 session 已清除
    resp = await app_client.get(f"/api/session/{sid}/state")
    assert resp.status_code == 200
    data = resp.json()
    assert data["evaluation_started"] is False
    assert data["evaluation_done"] is False


# ─── 限流 ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rate_limit(app_client, mock_llm):
    """超过频率限制后应返回限流提示。"""
    from unittest.mock import MagicMock, AsyncMock

    async def _stream(**kwargs):
        if kwargs.get("stream"):
            async def _gen():
                chunk = MagicMock()
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta.content = "ok"
                chunk.choices[0].delta.tool_calls = None
                yield chunk
            return _gen()
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = "ok"
        resp.choices[0].message.tool_calls = None
        return resp

    mock_llm.chat.completions.create = AsyncMock(side_effect=_stream)

    sid = f"rate-{uuid.uuid4().hex[:8]}"

    # 发送超过限制的请求（RATE_MAX = 20）
    for i in range(21):
        resp = await app_client.post("/api/chat", json={"session_id": sid, "message": f"msg-{i}"})
        assert resp.status_code == 200

    # 最后一条应被限流
    events = parse_sse_events(resp.text)
    content_texts = [e.get("text", "") for e in events if e.get("type") == "content"]
    full_reply = "".join(content_texts)
    assert "频繁" in full_reply or "限" in full_reply or "稍后" in full_reply, \
        f"应触发限流提示，实际: {full_reply[:100]}"


# ─── 评估报告端点 ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_evaluation_report_endpoint(app_client):
    """GET /evaluation/report/{session_id} 返回报告数据结构。"""
    sid = f"report-{uuid.uuid4().hex[:8]}"

    # 未评估的 session
    resp = await app_client.get(f"/evaluation/report/{sid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["evaluation_done"] is False
    assert data["evaluation_started"] is False
    assert "evaluation_report" in data


# ─── 评估后可正常对话 ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_after_evaluation(app_client, mock_llm):
    """评估完成后，应能继续正常对话。"""
    from unittest.mock import MagicMock, AsyncMock

    sid = f"post-eval-{uuid.uuid4().hex[:8]}"

    # 完成一个最简「用 AI」评估
    await app_client.post("/api/chat", json={"session_id": sid, "message": "评估"})
    await app_client.post("/api/chat", json={"session_id": sid, "message": "2"})  # 用 AI
    await app_client.post("/api/chat", json={"session_id": sid, "message": "1"})  # 选场景
    await app_client.post("/api/chat", json={"session_id": sid, "message": "1"})  # usage_time
    await app_client.post("/api/chat", json={"session_id": sid, "message": "1"})  # current_tools

    # 评估完成后，发送普通消息
    async def _stream(**kwargs):
        if kwargs.get("stream"):
            async def _gen():
                chunk = MagicMock()
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta.content = "评估已完成，有什么其他问题吗？"
                chunk.choices[0].delta.tool_calls = None
                yield chunk
            return _gen()
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = "评估已完成，有什么其他问题吗？"
        resp.choices[0].message.tool_calls = None
        return resp

    mock_llm.chat.completions.create = AsyncMock(side_effect=_stream)

    resp = await app_client.post("/api/chat", json={"session_id": sid, "message": "谢谢"})
    assert resp.status_code == 200
    events = parse_sse_events(resp.text)
    types = [e.get("type") for e in events]
    assert "content" in types, "评估后应能正常对话"


# ─── 数据库操作直接测试 ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_db_create_and_get_session(tmp_db):
    """直接测试数据库：创建会话并读取。"""
    import db

    await db.init_db()
    await db.create_session("test-db-001")
    data = await db.get_session("test-db-001")
    assert data is not None
    assert data["session_id"] == "test-db-001"
    assert data["evaluation_started"] is False

    # 更新
    await db.update_session("test-db-001", evaluation_started=True, evaluation_phase=3)
    data = await db.get_session("test-db-001")
    assert data["evaluation_started"] is True
    assert data["evaluation_phase"] == 3

    # 删除
    await db.delete_session("test-db-001")
    data = await db.get_session("test-db-001")
    assert data is None


@pytest.mark.asyncio
async def test_db_save_and_load_messages(tmp_db):
    """直接测试数据库：保存和加载消息。"""
    import db

    await db.init_db()
    await db.create_session("test-msg-001")
    await db.save_message("test-msg-001", "user", "你好")
    await db.save_message("test-msg-001", "assistant", "你好！")

    data = await db.get_session("test-msg-001")
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][0]["content"] == "你好"
    assert data["messages"][1]["role"] == "assistant"


# ─── get_or_create_session ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_or_create_session(tmp_db):
    """get_or_create_session：新 session 创建，已有 session 加载。"""
    import db
    from agent.schemas import SessionState

    await db.init_db()

    # 新建
    state = await db.get_or_create_session("new-session")
    assert isinstance(state, SessionState)
    assert state.session_id == "new-session"
    assert len(state.messages) == 0

    # 保存一些消息
    state.messages.append({"role": "user", "content": "测试"})
    # 通过 db 层保存
    await db.save_message("new-session", "user", "测试")

    # 再次获取
    state2 = await db.get_or_create_session("new-session")
    assert len(state2.messages) == 1
    assert state2.messages[0].content == "测试"
