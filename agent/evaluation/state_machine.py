"""评估状态机：问题驱动，管理「学 AI」和「用 AI」两条路径。"""

from typing import Optional, Tuple

from config import config
from agent.schemas import Message, SessionState


def is_evaluation_in_progress(state: SessionState) -> bool:
    """评估是否正在进行中。"""
    return state.evaluation_started and not state.evaluation_done


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


def _normalize(text: str) -> str:
    """去掉空格和标点，统一小写，用于模糊匹配。"""
    import re
    return re.sub(r'[\s:：,，。.!！?？、/·]', '', text).lower()


def _match_option(user_input: str, options: list) -> Optional[str]:
    """匹配用户输入（数字或文字）到选项文本。无匹配返回 None。"""
    # 1. 数字匹配
    try:
        parts = user_input.strip().split()
        if parts and parts[0].isdigit():
            idx = int(parts[0]) - 1
            if 0 <= idx < len(options):
                return options[idx]
    except (ValueError, IndexError):
        pass
    # 2. 归一化后子串匹配（去空格、标点）
    norm_input = _normalize(user_input)
    for opt in options:
        norm_opt = _normalize(opt)
        if norm_input in norm_opt or norm_opt in norm_input:
            return opt
    # 3. 关键词匹配（选项冒号前的部分）
    for opt in options:
        key = opt.split("：")[0].split(":")[0].strip()
        if _normalize(key) in norm_input or norm_input in _normalize(key):
            return opt
    return None


def _match_scenario(ans: str) -> Tuple[Optional[dict], int]:
    """匹配「用 AI」场景。无匹配返回 (None, -1)。"""
    # 1. 数字匹配
    try:
        parts = ans.strip().split()
        if parts and parts[0].isdigit():
            idx = int(parts[0]) - 1
            if 0 <= idx < len(config.USE_AI_SCENARIOS):
                return config.USE_AI_SCENARIOS[idx], idx
    except (ValueError, IndexError):
        pass
    # 2. 归一化子串匹配
    norm_input = _normalize(ans)
    for i, s in enumerate(config.USE_AI_SCENARIOS):
        norm_name = _normalize(s["name"])
        if norm_input in norm_name or norm_name in norm_input:
            return s, i
    # 3. 关键词匹配（/ 分隔的关键词）
    for i, s in enumerate(config.USE_AI_SCENARIOS):
        for part in s["name"].split("/"):
            kw = part.strip()[:4]
            if _normalize(kw) in norm_input:
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
            # 模糊判断：含"学"走学习路径，其他默认"用AI"
            norm = _normalize(ans)
            if "学" in norm and "用" not in norm:
                matched_path = first_q["options"][0]  # 学 AI
            else:
                matched_path = first_q["options"][1]  # 用 AI（默认）
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
                # 无匹配时用用户原话作为场景名
                scenario = {"name": message.strip(), "id": "custom"}
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
                # 无匹配时用用户原话
                matched = message.strip()
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
                # 无匹配时用用户原话
                matched = message.strip()
            state.evaluation_answers["current_tools"] = matched
            state.evaluation_done = True
            from agent.evaluation.report import render_use_ai_report
            report = await render_use_ai_report(state)
            state.evaluation_report = report
            state.messages.append(Message(role="assistant", content=report))
            yield {"type": "content", "text": report}
        return

    # ---- "学 AI" 路径：phase >= 1，遍历 LEARN_AI_QUESTIONS ----
    q_idx = phase - 1
    current_q = config.LEARN_AI_QUESTIONS[q_idx]
    matched = _match_option(message, current_q["options"])
    if not matched:
        # 无匹配时用用户原话
        matched = message.strip()
    state.evaluation_answers[current_q["id"]] = matched

    next_idx = q_idx + 1
    if next_idx >= len(config.LEARN_AI_QUESTIONS):
        from agent.evaluation.report import generate_report
        report = await generate_report(state)
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
