"""评估状态机：问题驱动，管理「学 AI」和「用 AI」两条路径。"""

from typing import Optional, Tuple

from config import config
from agent.schemas import Message, SessionState


def is_evaluation_in_progress(state: SessionState) -> bool:
    """评估是否正在进行中。"""
    return state.evaluation_started and not state.evaluation_done


# 问句标记：用户是在「先弄明白」，不是「要做问卷」
_QUESTION_MARKS = (
    "什么", "区别", "为什么", "怎么", "如何", "哪些", "多少",
    "是不是", "值不值", "吗", "？", "?",
)

# 显式请求评估：即使带问号也直接启动
EXPLICIT_EVAL = ("帮我评估", "我要评估", "评估一下", "做个评估", "开始评估")


def looks_like_question(message: str) -> bool:
    """判断这条消息是不是一个提问（提问不触发评估）。"""
    return any(t in message for t in _QUESTION_MARKS)


def should_start_evaluation(message: str) -> bool:
    """判断用户消息是否应触发评估。"""
    triggers = [
        "评估", "帮我看看", "学AI", "入门", "适不适合", "值不值得", "从哪开始",
        "方向", "规划", "学习路径", "零基础", "该怎么学",
        "帮我评估", "要不要学", "能不能学", "学不学",
        "有没有AI工具", "AI工具", "AI提效", "帮我提效",
        "推荐工具", "什么工具",
    ]
    msg_lower = message.lower()
    return any(t.lower() in msg_lower for t in triggers)


def _match_option(user_input: str, options: list) -> Optional[str]:
    """匹配用户输入（数字或文字）到选项文本。"""
    try:
        parts = user_input.strip().split()
        if parts and parts[0].isdigit():
            idx = int(parts[0]) - 1
            if 0 <= idx < len(options):
                return options[idx]
    except (ValueError, IndexError):
        pass
    for opt in options:
        if user_input in opt or opt in user_input:
            return opt
    return None


def _match_scenario(ans: str) -> Tuple[Optional[dict], int]:
    """匹配「用 AI」场景。"""
    try:
        parts = ans.strip().split()
        if parts and parts[0].isdigit():
            idx = int(parts[0]) - 1
            if 0 <= idx < len(config.USE_AI_SCENARIOS):
                return config.USE_AI_SCENARIOS[idx], idx
    except (ValueError, IndexError):
        pass
    for i, s in enumerate(config.USE_AI_SCENARIOS):
        kw = s["name"].split(" / ")[0].strip()[:4]
        if kw in ans:
            return s, i
    return None, -1


async def start_evaluation(state: SessionState, stream: bool = True):
    """开始评估：展示第一个问题。"""
    state.evaluation_phase = 0
    state.evaluation_started = True
    q = config.EVALUATION_FIRST_QUESTION
    reply = f"## 入门评估\n\n很高兴你想了解 AI！我先问你几个问题，帮你判断最适合的方向。\n\n**{q['question']}**\n\n"
    for i, opt in enumerate(q["options"], 1):
        reply += f"{i}. {opt}\n"
    reply += "\n请直接回答或选择对应的数字告诉我 ~"
    state.messages.append(Message(role="assistant", content=reply))
    yield {"type": "content", "text": reply}


async def continue_evaluation(state: SessionState, message: str, stream: bool = True):
    """继续评估：根据当前 phase 驱动问题流程。"""
    phase = state.evaluation_phase

    # phase == 0：刚回答第一个问题（学 vs 用）
    if phase == 0:
        ans = message.strip()
        first_q = config.EVALUATION_FIRST_QUESTION
        matched_path = _match_option(ans, first_q["options"])
        if not matched_path:
            reply = "没听清，再发一次？（输入数字或文字都行）"
            state.messages.append(Message(role="assistant", content=reply))
            yield {"type": "content", "text": reply}
            return
        is_use = "用 AI" in matched_path
        state.evaluation_path = "use" if is_use else "learn"
        state.evaluation_answers["path"] = matched_path
        state.evaluation_phase = 1

        if state.evaluation_path == "use":
            reply = "## 用 AI 场景选择\n\n你在什么场景需要 AI 帮忙？选一个：\n\n"
            for i, s in enumerate(config.USE_AI_SCENARIOS, 1):
                reply += f"{i}. {s['name']}\n"
            reply += "\n告诉我编号或场景名称就行 ~"
            state.messages.append(Message(role="assistant", content=reply))
            yield {"type": "content", "text": reply}
        else:
            q = config.LEARN_AI_QUESTIONS[0]
            reply = f"**{q['question']}**\n\n"
            for i, opt in enumerate(q["options"], 1):
                reply += f"{i}. {opt}\n"
            state.messages.append(Message(role="assistant", content=reply))
            yield {"type": "content", "text": reply}
        return

    # ---- "用 AI" 路径 ----
    if state.evaluation_path == "use":
        if phase == 1:
            scenario, _ = _match_scenario(message)
            if scenario is None:
                reply = "没听清，再发一次？（输入数字或文字都行）"
                state.messages.append(Message(role="assistant", content=reply))
                yield {"type": "content", "text": reply}
                return
            state.evaluation_answers["scenario"] = scenario["name"]
            state.evaluation_phase = 2
            q = config.USE_AI_QUESTIONS[0]
            reply = f"**{q['question']}**\n\n"
            for i, opt in enumerate(q["options"], 1):
                reply += f"{i}. {opt}\n"
            state.messages.append(Message(role="assistant", content=reply))
            yield {"type": "content", "text": reply}
        elif phase == 2:
            matched = _match_option(message, config.USE_AI_QUESTIONS[0]["options"])
            if not matched:
                reply = "没听清，再发一次？（输入数字或文字都行）"
                state.messages.append(Message(role="assistant", content=reply))
                yield {"type": "content", "text": reply}
                return
            state.evaluation_answers["usage_time"] = matched
            state.evaluation_phase = 3
            q = config.USE_AI_QUESTIONS[1]
            reply = f"**{q['question']}**\n\n"
            for i, opt in enumerate(q["options"], 1):
                reply += f"{i}. {opt}\n"
            state.messages.append(Message(role="assistant", content=reply))
            yield {"type": "content", "text": reply}
        elif phase == 3:
            matched = _match_option(message, config.USE_AI_QUESTIONS[1]["options"])
            if not matched:
                reply = "没听清，再发一次？（输入数字或文字都行）"
                state.messages.append(Message(role="assistant", content=reply))
                yield {"type": "content", "text": reply}
                return
            state.evaluation_answers["current_tools"] = matched
            state.evaluation_done = True
            from agent.evaluation.report import render_use_ai_report
            report = render_use_ai_report(state)
            state.evaluation_report = report
            state.messages.append(Message(role="assistant", content=report))
            yield {"type": "content", "text": report}
        return

    # ---- "学 AI" 路径：phase >= 1，遍历 LEARN_AI_QUESTIONS ----
    q_idx = phase - 1
    current_q = config.LEARN_AI_QUESTIONS[q_idx]
    matched = _match_option(message, current_q["options"])
    if not matched:
        reply = "没听清，再发一次？（输入数字或文字都行）"
        state.messages.append(Message(role="assistant", content=reply))
        yield {"type": "content", "text": reply}
        return
    state.evaluation_answers[current_q["id"]] = matched

    next_idx = q_idx + 1
    if next_idx >= len(config.LEARN_AI_QUESTIONS):
        from agent.evaluation.report import generate_report
        report = generate_report(state)
        state.evaluation_done = True
        state.evaluation_report = report
        state.messages.append(Message(role="assistant", content=report))
        yield {"type": "content", "text": report}
        return

    state.evaluation_phase += 1
    next_q = config.LEARN_AI_QUESTIONS[next_idx]
    reply = f"**{next_q['question']}**\n\n"
    for i, opt in enumerate(next_q["options"], 1):
        reply += f"{i}. {opt}\n"
    state.messages.append(Message(role="assistant", content=reply))
    yield {"type": "content", "text": reply}


# ─── 评估进行中的统一入口（带逃生阀）────────────────────────────────

def _matches_current(state: SessionState, message: str) -> bool:
    """判断输入是否是当前问题的合法答案（复用已有匹配函数，不改其逻辑）。"""
    phase = state.evaluation_phase

    if phase == 0:
        return _match_option(message.strip(), config.EVALUATION_FIRST_QUESTION["options"]) is not None

    if state.evaluation_path == "use":
        if phase == 1:
            scenario, _ = _match_scenario(message)
            return scenario is not None
        if phase == 2:
            return _match_option(message, config.USE_AI_QUESTIONS[0]["options"]) is not None
        if phase == 3:
            return _match_option(message, config.USE_AI_QUESTIONS[1]["options"]) is not None
        return False

    q_idx = phase - 1
    if 0 <= q_idx < len(config.LEARN_AI_QUESTIONS):
        return _match_option(message, config.LEARN_AI_QUESTIONS[q_idx]["options"]) is not None
    return False


def current_question_text(state: SessionState) -> str:
    """当前正在问的问题：取最后一条助手消息（每题都已落库）。"""
    for m in reversed(state.messages):
        if m.role == "assistant" and m.content.strip():
            return m.content.strip()
    return ""


async def continue_evaluation_with_fallback(state: SessionState, message: str, stream: bool = True):
    """评估进行中的分发：能作答就作答；是提问就先回答再回到评估。"""
    if _matches_current(state, message):
        async for chunk in continue_evaluation(state, message, stream):
            yield chunk
        return

    if looks_like_question(message):
        question_text = current_question_text(state)  # 先取，normal_chat 之后会追加回答
        from agent.core import normal_chat  # 延迟导入，避免与 core 形成导入环
        async for chunk in normal_chat(state, message, stream):
            yield chunk
        if question_text:
            reply = f"\n\n---\n（回到刚才的问题）\n\n{question_text}"
            state.messages.append(Message(role="assistant", content=reply))
            yield {"type": "content", "text": reply}
        return

    async for chunk in continue_evaluation(state, message, stream):
        yield chunk
