"""agent/llm_client.py 单元测试：重试逻辑、消息截断。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from agent.schemas import Message


# ─── build_messages 测试 ──────────────────────────────────────────────

class TestBuildMessages:
    """测试消息截断逻辑。"""

    def test_empty_messages(self):
        from agent.llm_client import build_messages
        msgs = build_messages([], "你是助手")
        assert len(msgs) == 1
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "你是助手"

    def test_within_limit(self):
        from agent.llm_client import build_messages
        messages = [
            Message(role="user", content="你好"),
            Message(role="assistant", content="你好！"),
        ]
        msgs = build_messages(messages, "系统提示")
        assert len(msgs) == 3  # system + 2 messages
        assert msgs[0]["role"] == "system"
        assert msgs[1]["content"] == "你好"
        assert msgs[2]["content"] == "你好！"

    def test_truncate_by_count(self):
        from agent.llm_client import build_messages
        messages = [Message(role="user", content=f"msg-{i}") for i in range(30)]
        msgs = build_messages(messages, "系统", max_messages=5)
        # system + truncation notice + 5 messages
        assert len(msgs) == 7
        assert "省略" in msgs[1]["content"]
        assert msgs[2]["content"] == "msg-25"  # 最近 5 条从 msg-25 开始

    def test_truncate_by_chars(self):
        from agent.llm_client import build_messages
        messages = [
            Message(role="user", content="a" * 3000),
            Message(role="assistant", content="b" * 3000),
            Message(role="user", content="c" * 3000),
        ]
        msgs = build_messages(messages, "系统", max_chars=5000)
        # system + truncation notice + last 2 messages (6000 chars > 5000, so only last 1 or 2)
        content_roles = [m["role"] for m in msgs if m["role"] != "system"]
        # 应该截断了部分消息
        assert len(content_roles) < 3

    def test_no_truncation_notice_when_not_truncated(self):
        from agent.llm_client import build_messages
        messages = [Message(role="user", content="短消息")]
        msgs = build_messages(messages, "系统")
        # 没有省略提示
        assert not any("省略" in m.get("content", "") for m in msgs)

    def test_system_prompt_always_first(self):
        from agent.llm_client import build_messages
        messages = [Message(role="user", content="hello")] * 25
        msgs = build_messages(messages, "我是系统提示", max_messages=10)
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "我是系统提示"


# ─── ask_llm 重试测试 ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ask_llm_success():
    """正常调用应直接返回内容。"""
    from agent.llm_client import ask_llm

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = "成功"
    mock_resp.choices[0].message.tool_calls = None
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

    with patch("agent.llm_client.get_client", return_value=mock_client), \
         patch("agent.llm_client.config") as mock_config:
        mock_config.LLM_MODEL = "test-model"
        result = await ask_llm([{"role": "user", "content": "hi"}])
        assert result == "成功"


@pytest.mark.asyncio
async def test_ask_llm_retries_on_rate_limit():
    """RateLimitError 应触发重试。"""
    from openai import RateLimitError
    from agent.llm_client import ask_llm

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = "成功"
    mock_resp.choices[0].message.tool_calls = None

    # 前两次限流，第三次成功
    mock_client.chat.completions.create = AsyncMock(
        side_effect=[
            RateLimitError(message="rate limited", response=MagicMock(status_code=429), body=None),
            RateLimitError(message="rate limited", response=MagicMock(status_code=429), body=None),
            mock_resp,
        ]
    )

    with patch("agent.llm_client.get_client", return_value=mock_client), \
         patch("agent.llm_client.config") as mock_config, \
         patch("agent.llm_client.asyncio.sleep", new_callable=AsyncMock):
        mock_config.LLM_MODEL = "test-model"
        result = await ask_llm([{"role": "user", "content": "hi"}], max_retries=3)
        assert result == "成功"
        assert mock_client.chat.completions.create.call_count == 3


@pytest.mark.asyncio
async def test_ask_llm_no_retry_on_400():
    """400 错误不应重试。"""
    from openai import APIStatusError
    from agent.llm_client import ask_llm

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=APIStatusError(
            message="bad request",
            response=MagicMock(status_code=400),
            body=None,
        )
    )

    with patch("agent.llm_client.get_client", return_value=mock_client), \
         patch("agent.llm_client.config") as mock_config:
        mock_config.LLM_MODEL = "test-model"
        with pytest.raises(APIStatusError):
            await ask_llm([{"role": "user", "content": "hi"}], max_retries=3)
        # 只调用 1 次，不重试
        assert mock_client.chat.completions.create.call_count == 1
