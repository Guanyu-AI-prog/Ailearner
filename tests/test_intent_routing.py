"""意图路由测试：提问 vs 作答、评估逃生阀、退出词。

对应修复：ailearner-意图路由修复-方案与记录.md
"""

import pytest

from agent.schemas import Message, SessionState
from agent import core, orchestrator
from agent.evaluation.state_machine import looks_like_question
from agent.orchestrator import handle_message


async def _fake_normal_chat(state, message, stream=True):
    """替身：不调 LLM，直接产出可识别的回复。"""
    text = f"[FAKE-普通对话] {message}"
    state.messages.append(Message(role="assistant", content=text))
    yield {"type": "content", "text": text}


@pytest.fixture
def fake_chat(monkeypatch):
    """替换普通对话。

    要同时替换两处：
    - `agent.orchestrator.normal_chat`：orchestrator 模块导入时已绑定引用
    - `agent.core.normal_chat`：状态机逃生阀是调用时 `from agent.core import normal_chat`
    """
    monkeypatch.setattr(orchestrator, "normal_chat", _fake_normal_chat)
    monkeypatch.setattr(core, "normal_chat", _fake_normal_chat)
    return _fake_normal_chat


async def _collect(state, message):
    events = []
    async for e in handle_message(state, message):
        events.append(e)
    return "".join(e.get("text", "") for e in events)


# ─── looks_like_question ──────────────────────────────────────────────

class TestLooksLikeQuestion:
    @pytest.mark.parametrize("msg", [
        "用AI跟学AI有什么区别?",
        "用AI跟学AI的区别在哪里?",
        "零基础该怎么学",
        "这个值不值得学吗",
        "有哪些方向",
    ])
    def test_question_detected(self, msg):
        assert looks_like_question(msg) is True

    @pytest.mark.parametrize("msg", [
        "帮我评估",
        "我要评估一下",
        "我是做运营的，想学 AI",
        "1",
    ])
    def test_non_question(self, msg):
        assert looks_like_question(msg) is False


# ─── 首轮：提问不启动评估 ─────────────────────────────────────────────

class TestFirstTurnRouting:
    @pytest.mark.asyncio
    async def test_question_does_not_start_evaluation(self, fake_chat):
        state = SessionState(session_id="t1")

        reply = await _collect(state, "用AI跟学AI有什么区别?")

        assert state.evaluation_started is False, "提问不应启动评估"
        assert "[FAKE-普通对话]" in reply

    @pytest.mark.asyncio
    async def test_trigger_word_with_question_gets_hint(self, fake_chat):
        state = SessionState(session_id="t2")

        reply = await _collect(state, "零基础该怎么学")

        assert state.evaluation_started is False
        assert "[FAKE-普通对话]" in reply
        assert "帮我评估" in reply, "应软引导一次评估"

    @pytest.mark.asyncio
    async def test_explicit_request_starts_evaluation(self):
        state = SessionState(session_id="t3")

        reply = await _collect(state, "帮我评估")

        assert state.evaluation_started is True
        assert state.evaluation_phase == 0
        assert "入门评估" in reply

    @pytest.mark.asyncio
    async def test_normal_chat_when_nothing_matches(self, fake_chat):
        state = SessionState(session_id="t4")

        reply = await _collect(state, "今天天气不错")

        assert state.evaluation_started is False
        assert "[FAKE-普通对话]" in reply


# ─── 评估进行中：逃生阀 ───────────────────────────────────────────────

class TestEscapeHatch:
    def _in_progress_state(self, sid="t5"):
        state = SessionState(session_id=sid, evaluation_started=True, evaluation_phase=0)
        state.messages.append(
            Message(role="assistant", content="**你想「学 AI」还是「用 AI」？**\n1. 学 AI\n2. 用 AI")
        )
        return state

    @pytest.mark.asyncio
    async def test_question_answered_and_returns_to_evaluation(self, fake_chat):
        state = self._in_progress_state()

        reply = await _collect(state, "用AI跟学AI的区别在哪里?")

        assert "[FAKE-普通对话]" in reply, "应先回答问题"
        assert "回到刚才的问题" in reply, "应重贴当前问题"
        assert "学 AI」还是「用 AI" in reply
        assert state.evaluation_phase == 0, "phase 不应变化"
        assert state.evaluation_started is True

    @pytest.mark.asyncio
    async def test_valid_answer_still_advances(self):
        state = self._in_progress_state(sid="t6")

        reply = await _collect(state, "1")

        assert state.evaluation_phase == 1, "正常作答应推进"
        assert state.evaluation_path == "learn"
        assert "[FAKE" not in reply

    @pytest.mark.asyncio
    async def test_garbage_input_still_reprompts(self):
        state = self._in_progress_state(sid="t7")

        reply = await _collect(state, "xyz")

        assert "没听清" in reply
        assert state.evaluation_phase == 0


# ─── 退出词 ──────────────────────────────────────────────────────────

class TestExitWords:
    @pytest.mark.asyncio
    async def test_exit_resets_evaluation(self, fake_chat):
        state = SessionState(
            session_id="t8", evaluation_started=True, evaluation_phase=2,
            evaluation_path="use", evaluation_answers={"path": "用 AI"},
        )

        reply = await _collect(state, "跳过")

        assert state.evaluation_started is False
        assert state.evaluation_phase == 0
        assert state.evaluation_path == ""
        assert state.evaluation_answers == {}
        assert "[FAKE-普通对话]" in reply
