"""评估状态机单元测试：覆盖所有路径。"""

import pytest
from agent.schemas import Message, SessionState
from agent.evaluation.state_machine import (
    is_evaluation_in_progress,
    should_start_evaluation,
    _match_option,
    _match_scenario,
    start_evaluation,
    continue_evaluation,
)


# ─── is_evaluation_in_progress ────────────────────────────────────────

class TestIsEvaluationInProgress:
    def test_not_started(self):
        state = SessionState(session_id="test")
        assert is_evaluation_in_progress(state) is False

    def test_started_not_done(self):
        state = SessionState(session_id="test", evaluation_started=True, evaluation_done=False)
        assert is_evaluation_in_progress(state) is True

    def test_started_and_done(self):
        state = SessionState(session_id="test", evaluation_started=True, evaluation_done=True)
        assert is_evaluation_in_progress(state) is False


# ─── should_start_evaluation ─────────────────────────────────────────

class TestShouldStartEvaluation:
    def test_keyword_eval(self):
        assert should_start_evaluation("帮我评估一下") is True

    def test_keyword_learn(self):
        assert should_start_evaluation("我想学AI") is True

    def test_keyword_direction(self):
        assert should_start_evaluation("不知道方向") is True

    def test_keyword_tool(self):
        assert should_start_evaluation("有什么AI工具") is True

    def test_normal_message(self):
        assert should_start_evaluation("你好") is False

    def test_empty_message(self):
        assert should_start_evaluation("") is False

    def test_partial_match(self):
        assert should_start_evaluation("我想入门") is True


# ─── _match_option ────────────────────────────────────────────────────

class TestMatchOption:
    def test_numeric_first(self):
        options = ["A", "B", "C"]
        assert _match_option("1", options) == "A"

    def test_numeric_last(self):
        options = ["A", "B", "C"]
        assert _match_option("3", options) == "C"

    def test_out_of_range(self):
        options = ["A", "B"]
        assert _match_option("5", options) is None

    def test_zero(self):
        options = ["A", "B"]
        assert _match_option("0", options) is None

    def test_text_match(self):
        options = ["上班族", "学生", "自由职业"]
        assert _match_option("我是学生", options) == "学生"

    def test_exact_match(self):
        options = ["ChatGPT", "文心一言"]
        assert _match_option("ChatGPT", options) == "ChatGPT"

    def test_no_match(self):
        options = ["A", "B"]
        assert _match_option("完全无关", options) is None

    def test_empty_input(self):
        """空字符串会匹配第一个选项（"" in any_string 为 True）。"""
        options = ["A", "B"]
        assert _match_option("", options) == "A"


# ─── _match_scenario ─────────────────────────────────────────────────

class TestMatchScenario:
    def test_numeric_first(self):
        scenario, idx = _match_scenario("1")
        assert scenario is not None
        assert idx == 0

    def test_numeric_out_of_range(self):
        scenario, idx = _match_scenario("99")
        assert scenario is None
        assert idx == -1

    def test_text_match(self):
        scenario, idx = _match_scenario("文章修改")
        assert scenario is not None
        assert scenario["id"] == "article_edit"

    def test_no_match(self):
        scenario, idx = _match_scenario("xyz")
        assert scenario is None
        assert idx == -1


# ─── start_evaluation ────────────────────────────────────────────────

class TestStartEvaluation:
    @pytest.mark.asyncio
    async def test_sets_state(self):
        state = SessionState(session_id="test")
        events = []
        async for event in start_evaluation(state):
            events.append(event)

        assert state.evaluation_started is True
        assert state.evaluation_phase == 0
        assert len(events) == 1
        assert events[0]["type"] == "content"
        assert "学 AI" in events[0]["text"] or "用 AI" in events[0]["text"]

    @pytest.mark.asyncio
    async def test_appends_message(self):
        state = SessionState(session_id="test")
        async for _ in start_evaluation(state):
            pass
        assert len(state.messages) == 1
        assert state.messages[0].role == "assistant"


# ─── continue_evaluation: phase 0 (学 vs 用) ─────────────────────────

class TestContinueEvaluationPhase0:
    @pytest.mark.asyncio
    async def test_choose_use_ai(self):
        state = SessionState(session_id="test", evaluation_started=True, evaluation_phase=0)
        state.messages.append(Message(role="user", content="2"))

        events = []
        async for event in continue_evaluation(state, "2"):
            events.append(event)

        assert state.evaluation_path == "use"
        assert state.evaluation_phase == 1
        assert "场景" in events[0]["text"]

    @pytest.mark.asyncio
    async def test_choose_learn_ai(self):
        state = SessionState(session_id="test", evaluation_started=True, evaluation_phase=0)
        state.messages.append(Message(role="user", content="1"))

        events = []
        async for event in continue_evaluation(state, "1"):
            events.append(event)

        assert state.evaluation_path == "learn"
        assert state.evaluation_phase == 1
        # 应该展示 LEARN_AI_QUESTIONS[0]
        assert "学 AI" in events[0]["text"] or "为了什么" in events[0]["text"]

    @pytest.mark.asyncio
    async def test_invalid_input_reprompts(self):
        state = SessionState(session_id="test", evaluation_started=True, evaluation_phase=0)
        state.messages.append(Message(role="user", content="xyz"))

        events = []
        async for event in continue_evaluation(state, "xyz"):
            events.append(event)

        assert "没听清" in events[0]["text"]
        # phase 不变
        assert state.evaluation_phase == 0


# ─── continue_evaluation: "用 AI" 路径 ───────────────────────────────

class TestContinueEvaluationUsePath:
    @pytest.mark.asyncio
    async def test_phase1_select_scenario(self):
        state = SessionState(
            session_id="test", evaluation_started=True,
            evaluation_phase=1, evaluation_path="use",
        )
        state.messages.append(Message(role="user", content="1"))

        events = []
        async for event in continue_evaluation(state, "1"):
            events.append(event)

        assert state.evaluation_phase == 2
        assert "scenario" in state.evaluation_answers

    @pytest.mark.asyncio
    async def test_phase1_invalid_reprompts(self):
        state = SessionState(
            session_id="test", evaluation_started=True,
            evaluation_phase=1, evaluation_path="use",
        )
        state.messages.append(Message(role="user", content="xyz"))

        events = []
        async for event in continue_evaluation(state, "xyz"):
            events.append(event)

        assert "没听清" in events[0]["text"]
        assert state.evaluation_phase == 1

    @pytest.mark.asyncio
    async def test_phase2_answer_usage_time(self):
        state = SessionState(
            session_id="test", evaluation_started=True,
            evaluation_phase=2, evaluation_path="use",
            evaluation_answers={"scenario": "文章修改 / 润色 / 重写"},
        )
        state.messages.append(Message(role="user", content="2"))

        events = []
        async for event in continue_evaluation(state, "2"):
            events.append(event)

        assert state.evaluation_phase == 3
        assert "usage_time" in state.evaluation_answers

    @pytest.mark.asyncio
    async def test_phase3_answer_tools_generates_report(self):
        state = SessionState(
            session_id="test", evaluation_started=True,
            evaluation_phase=3, evaluation_path="use",
            evaluation_answers={"scenario": "文章修改 / 润色 / 重写", "usage_time": "每天用一点"},
        )
        state.messages.append(Message(role="user", content="1"))

        events = []
        async for event in continue_evaluation(state, "1"):
            events.append(event)

        assert state.evaluation_done is True
        assert state.evaluation_report != ""
        assert "使用评估" in events[0]["text"] or "模板" in events[0]["text"]


# ─── continue_evaluation: "学 AI" 路径 ───────────────────────────────

class TestContinueEvaluationLearnPath:
    @pytest.mark.asyncio
    async def test_answer_first_question(self):
        state = SessionState(
            session_id="test", evaluation_started=True,
            evaluation_phase=1, evaluation_path="learn",
        )
        state.messages.append(Message(role="user", content="2"))

        events = []
        async for event in continue_evaluation(state, "2"):
            events.append(event)

        assert state.evaluation_phase == 2
        assert "goal" in state.evaluation_answers

    @pytest.mark.asyncio
    async def test_invalid_input_reprompts(self):
        state = SessionState(
            session_id="test", evaluation_started=True,
            evaluation_phase=1, evaluation_path="learn",
        )
        state.messages.append(Message(role="user", content="xyz"))

        events = []
        async for event in continue_evaluation(state, "xyz"):
            events.append(event)

        assert "没听清" in events[0]["text"]
        assert state.evaluation_phase == 1

    @pytest.mark.asyncio
    async def test_full_learn_path_generates_report(self):
        """完整走完 7 道题，应生成报告。"""
        state = SessionState(
            session_id="test", evaluation_started=True,
            evaluation_phase=1, evaluation_path="learn",
        )

        # 7 道题的默认答案
        answers = ["2", "1", "3", "2", "2", "2", "1"]
        for i, ans in enumerate(answers):
            state.messages.append(Message(role="user", content=ans))
            events = []
            async for event in continue_evaluation(state, ans):
                events.append(event)

        assert state.evaluation_done is True
        assert state.evaluation_report != ""
        assert "评估" in state.evaluation_report or "建议" in state.evaluation_report


# ─── 边界条件 ─────────────────────────────────────────────────────────

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_numeric_with_extra_text(self):
        """数字后跟文字仍应匹配。"""
        state = SessionState(session_id="test", evaluation_started=True, evaluation_phase=0)
        state.messages.append(Message(role="user", content="1 我想学"))

        events = []
        async for event in continue_evaluation(state, "1 我想学"):
            events.append(event)

        assert state.evaluation_path == "learn"

    @pytest.mark.asyncio
    async def test_state_persists_across_calls(self):
        """多次调用 continue_evaluation，状态应累积。"""
        state = SessionState(
            session_id="test", evaluation_started=True,
            evaluation_phase=0, evaluation_path="",
        )
        state.messages.append(Message(role="user", content="2"))

        # 第一次：选「用 AI」
        async for _ in continue_evaluation(state, "2"):
            pass
        assert state.evaluation_path == "use"
        assert state.evaluation_phase == 1

        # 第二次：选场景
        state.messages.append(Message(role="user", content="1"))
        async for _ in continue_evaluation(state, "1"):
            pass
        assert state.evaluation_phase == 2
        assert "scenario" in state.evaluation_answers
