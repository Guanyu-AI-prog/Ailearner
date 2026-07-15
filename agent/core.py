import json
from typing import Dict, List, Optional
from openai import AsyncOpenAI
from config import config
from agent.schemas import Message, SessionState
from agent.prompts import SYSTEM_PROMPT
from agent.tools import TOOL_DEFINITIONS, execute_tool
from knowledge.retriever import retrieve_knowledge


_llm_client = None


def get_client():
    global _llm_client
    if _llm_client is None:
        _llm_client = AsyncOpenAI(
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL,
        )
    return _llm_client


async def ask_llm(messages: List[Dict], tools: Optional[List] = None, stream: bool = False, model: Optional[str] = None):
    client = get_client()
    kwargs = {
        "model": model or config.LLM_MODEL,
        "messages": messages,
        "stream": stream,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    return await client.chat.completions.create(**kwargs)


async def generate_stream(messages: List[Dict], tools: Optional[List] = None):
    response = await ask_llm(messages, tools=tools, stream=True)
    tool_calls_buffer = {}
    async for chunk in response:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta is None:
            continue
        if delta.content:
            yield {"type": "content", "text": delta.content}
        if delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index
                if idx not in tool_calls_buffer:
                    tool_calls_buffer[idx] = {"id": "", "name": "", "arguments": ""}
                if tc.id:
                    tool_calls_buffer[idx]["id"] = tc.id
                if tc.function.name:
                    tool_calls_buffer[idx]["name"] += tc.function.name
                if tc.function.arguments:
                    tool_calls_buffer[idx]["arguments"] += tc.function.arguments
    if tool_calls_buffer:
        for tc_data in tool_calls_buffer.values():
            yield {"type": "tool_call", "name": tc_data["name"], "arguments": tc_data["arguments"]}


def is_evaluation_in_progress(state: SessionState) -> bool:
    return state.evaluation_started and not state.evaluation_done


def should_start_evaluation(message: str) -> bool:
    triggers = ["评估", "帮我看看", "学AI", "入门", "适不适合", "值不值得", "从哪开始",
                 "方向", "规划", "学习路径", "零基础", "该怎么学",
                 "帮我评估", "要不要学", "能不能学", "学不学",
                 "有没有AI工具", "AI工具", "AI提效", "帮我提效",
                 "推荐工具", "什么工具"]
    msg_lower = message.lower()
    for t in triggers:
        if t.lower() in msg_lower:
            return True
    return False


async def build_context(state: SessionState, user_message: str) -> str:
    relevant = retrieve_knowledge(user_message, n_results=3)
    if not relevant:
        return ""
    context = "以下是从知识库中找到的相关信息：\n\n"
    for doc, metadata in relevant:
        tags = ", ".join(metadata.get("tags", []))
        context += f"---\n来源：{metadata.get('title', '未知')}\n"
        if tags:
            context += f"标签：{tags}\n"
        context += f"{doc}\n\n"
    context += "请基于以上信息回答用户问题。如果信息不够，可以告诉用户你需要搜索。"
    return context


async def handle_message(state: SessionState, message: str, stream: bool = True):
    state.messages.append(Message(role="user", content=message))

    if state.evaluation_done:
        gen = normal_chat(state, message, stream)
    elif is_evaluation_in_progress(state):
        gen = continue_evaluation(state, message, stream)
    elif should_start_evaluation(message):
        gen = start_evaluation(state, stream)
    else:
        gen = normal_chat(state, message, stream)
    async for chunk in gen:
        yield chunk


def _resolve_answer(answer: str, options: list) -> str:
    """Resolve a stored answer (possibly raw number) to the full option text."""
    if not answer:
        return ""
    matched = _match_option(answer, options)
    return matched or answer


async def normal_chat(state: SessionState, message: str, stream: bool = True):
    context = await build_context(state, message)
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in state.messages[:-1]:
        msgs.append({"role": m.role, "content": m.content})
    user_content = message
    if context:
        user_content = f"{message}\n\n{context}"
    msgs.append({"role": "user", "content": user_content})

    if stream:
        full_content = ""
        tool_calls_buffer = []
        async for chunk in generate_stream(msgs, tools=TOOL_DEFINITIONS):
            if chunk["type"] == "content":
                full_content += chunk["text"]
                yield {"type": "content", "text": chunk["text"]}
            elif chunk["type"] == "tool_call":
                tool_calls_buffer.append(chunk)

        if tool_calls_buffer:
            assistant_tool_calls = []
            tool_results = []
            for tc in tool_calls_buffer:
                tc_id = tc.get("id", "") or f"call_{tc['name']}"
                assistant_tool_calls.append({
                    "id": tc_id, "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]}
                })
                yield {"type": "status", "text": f"\n\n> 正在调用工具：{tc['name']}..."}
                result = await execute_tool(tc["name"], tc["arguments"])
                tool_results.append({"tool_call_id": tc_id, "content": result})
                yield {"type": "status", "text": f"> 工具 {tc['name']} 执行完成\n\n"}

            msgs.append({"role": "assistant", "content": None, "tool_calls": assistant_tool_calls})
            for tr in tool_results:
                msgs.append({"role": "tool", **tr})

            yield {"type": "status", "text": "> 正在生成回复...\n\n"}
            async for chunk2 in generate_stream(msgs):
                if chunk2["type"] == "content":
                    full_content += chunk2["text"]
                    yield chunk2

        state.messages.append(Message(role="assistant", content=full_content))
    else:
        response = await ask_llm(msgs, tools=TOOL_DEFINITIONS)
        msg = response.choices[0].message
        if msg.tool_calls:
            assistant_tool_calls = [tc.model_dump() for tc in msg.tool_calls]
            msgs.append({"role": "assistant", "content": None, "tool_calls": assistant_tool_calls})
            for tc in msg.tool_calls:
                result = await execute_tool(tc.function.name, tc.function.arguments)
                msgs.append({"role": "tool", "tool_call_id": tc.id, "content": result})
            response = await ask_llm(msgs)
            content = response.choices[0].message.content or ""
        else:
            content = msg.content or ""
        state.messages.append(Message(role="assistant", content=content))
        yield {"type": "content", "text": content}


async def start_evaluation(state: SessionState, stream: bool = True):
    state.evaluation_phase = 0
    state.evaluation_started = True
    q = config.EVALUATION_FIRST_QUESTION
    reply = f"## 入门评估\n\n很高兴你想了解 AI！我先问你几个问题，帮你判断最适合的方向。\n\n**{q['question']}**\n\n"
    for i, opt in enumerate(q["options"], 1):
        reply += f"{i}. {opt}\n"
    reply += "\n请直接回答或选择对应的数字告诉我 ~"
    state.messages.append(Message(role="assistant", content=reply))
    yield {"type": "content", "text": reply}


def _match_option(user_input: str, options: list) -> Optional[str]:
    """Match user input (number or partial text) to the full option text."""
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


def _match_scenario(ans: str):
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


async def continue_evaluation(state: SessionState, message: str, stream: bool = True):
    phase = state.evaluation_phase
    # phase == 0  means they just answered the very first question (学 vs 用)
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

    # ---- "用 AI" path ----
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
            report = _render_use_ai_report(state)
            state.evaluation_report = report
            state.messages.append(Message(role="assistant", content=report))
            yield {"type": "content", "text": report}
        return

    # ---- "学 AI" path: phase >= 1, cycling through LEARN_AI_QUESTIONS ----
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


def _render_prompt_template(scenario: dict) -> str:
    params_text = "\n".join(
        f"  - `{{{k}}}`：{' / '.join(v)}" if isinstance(v, list) else f"  - `{{{k}}}`：{v}"
        for k, v in scenario["parameters"].items()
    )
    return f"""## 你的专属 Prompt 模板

### 场景：{scenario['name']}

复制以下模板，把用 `{{}}` 标记的参数替换成你的内容就行：

---

```markdown
{scenario['prompt']}
```

---

### 参数说明

{params_text}

---

### 使用建议

{scenario['advice']}

---

**提示**：把这个模板收藏起来，每次用到直接复制，填上具体内容就能用。
"""


def _render_use_ai_report(state: SessionState) -> str:
    scenario_name = state.evaluation_answers.get("scenario", "")
    usage_time = state.evaluation_answers.get("usage_time", "")
    current_tools = state.evaluation_answers.get("current_tools", "")

    scenario = None
    for s in config.USE_AI_SCENARIOS:
        if s["name"] == scenario_name:
            scenario = s
            break
    if not scenario:
        scenario = config.USE_AI_SCENARIOS[0]

    prompt_template = _render_prompt_template(scenario)

    time_advice_map = {
        "偶尔试一下": "你目前使用AI的频率不高，可以从这个模板开始，遇到具体场景时套用试试。",
        "每天用一点": "你已经有一定使用习惯，建议把这个模板收藏起来，逐步融入日常工作流。",
        "经常用": "你已经是AI的活跃用户了，可以尝试用Agent工具把多个模板串联成自动化工作流。",
        "重度依赖": "建议深入研究API调用和自定义Agent开发，把AI深度嵌入业务流程。",
    }
    tool_advice_map = {
        "没用过": "建议先用这个模板体验一下AI的效果，熟悉后再探索更多功能。",
        "ChatGPT": "可以直接把模板粘贴到ChatGPT中使用，效果很好。",
        "文心一言": "模板对文心一言同样适用，注意调整语气参数以获得最佳效果。",
        "通义千问": "模板对通义千问同样适用，注意调整语气参数以获得最佳效果。",
        "Kimi": "Kimi擅长长文本处理，这个模板配合Kimi会有不错的效果。",
        "其他": "模板通用于主流AI工具，直接粘贴使用即可。",
    }

    time_advice = time_advice_map.get(usage_time, "")
    tool_advice = tool_advice_map.get(current_tools, "模板通用于主流AI工具，直接粘贴使用即可。")

    if usage_time in ("偶尔试一下",) and current_tools == "没用过":
        intensity = "轻度尝试"
        intensity_desc = "先体验，再决定是否深入。"
    elif usage_time in ("经常用", "重度依赖"):
        intensity = "深度使用"
        intensity_desc = "AI已经是你的得力助手，建议持续深化。"
    else:
        intensity = "积极使用"
        intensity_desc = "建议逐步将AI融入日常工作流。"

    report = f"""## 使用评估

**推荐强度**：{intensity}

{intensity_desc}

---

**使用频率**：{usage_time}

**当前工具**：{current_tools}

---

### 使用建议

{time_advice}

{tool_advice}

---
"""
    report += prompt_template
    return report


DIRECTION_MAP = {
    "文字相关": "NLP/LLM 应用方向",
    "图像相关": "计算机视觉方向",
    "数据分析": "数据分析/机器学习方向",
    "声音相关": "语音技术方向",
    "AI 产品设计": "AI 产品方向",
    "还没特定方向": "通用入门",
}

LEVEL_MAP = {
    "转行": "L3 进阶",
    "工作效率": "L2 入门",
    "学术研究": "L4 专业",
    "纯粹好奇": "L1 科普",
    "先了解看看": "L1 科普",
}

LEVEL_ABILITY = {
    "L1 科普": {"ability": "能用AI工具写文案、总结文档、翻译，日常办公提效", "salary": ""},
    "L2 入门": {"ability": "能用Agent工具搭建简单工作流，帮公司做内部AI工具", "salary": ""},
    "L3 进阶": {"ability": "能独立部署AI应用到生产环境，能接AI外包项目", "salary": "6-10K薪资区间"},
    "L4 专业": {"ability": "能做AI系统架构设计，需要持续学习", "salary": "10K+"},
}

async def generate_report(state: SessionState) -> str:
    answers = state.evaluation_answers

    # Resolve raw numbers to full option text for display
    goal = _resolve_answer(answers.get("goal", ""), config.LEARN_AI_QUESTIONS[0]["options"])
    bg = _resolve_answer(answers.get("background", ""), config.LEARN_AI_QUESTIONS[1]["options"])
    time_val = _resolve_answer(answers.get("time", ""), config.LEARN_AI_QUESTIONS[2]["options"])
    math_lev = _resolve_answer(answers.get("math_level", ""), config.LEARN_AI_QUESTIONS[3]["options"])
    prog_lev = _resolve_answer(answers.get("programming_level", ""), config.LEARN_AI_QUESTIONS[4]["options"])
    budget = _resolve_answer(answers.get("budget", ""), config.LEARN_AI_QUESTIONS[5]["options"])
    direction = _resolve_answer(answers.get("direction", ""), config.LEARN_AI_QUESTIONS[6]["options"])

    UNKNOWN = {"不知道", ""}
    all_vals = [goal, bg, time_val, math_lev, prog_lev, budget, direction]
    meaningful = sum(1 for v in all_vals if v and v not in UNKNOWN)
    unknown_ratio = 1 - meaningful / max(len(all_vals), 1)

    direction_name = "通用入门"
    for key, val in DIRECTION_MAP.items():
        if key in direction:
            direction_name = val
            break

    level = "L1 科普"
    for key, val in LEVEL_MAP.items():
        if key in goal:
            level = val
            break

    if prog_lev and ("零基础" in prog_lev or "能看懂" in prog_lev) and level in ("L3 进阶", "L4 专业"):
        level = "L2 入门"
    if time_val and "少于 2" in time_val:
        level = "L1 科普"
    if budget and "零成本" in budget:
        level = "L2 入门"
    if unknown_ratio > 0.5:
        level = "L1 科普"

    goal_uncertain = any(kw in goal for kw in ["还没想清楚", "纯粹好奇", "不知道", "了解看看"]) if goal else True
    if unknown_ratio > 0.5:
        should = "信息不足，暂无法给出明确建议"
    elif goal_uncertain:
        should = "先了解看看，不建议盲目投入"
    else:
        should = "建议学"

    steps = {
        "L1 科普": [
            "使用 Agent 型 AI（如 hermes / OpenClaw），比对话式聊天更能理解 AI 的能力边界",
            "申请第一个 API Key（推荐小米 MiMo 开放平台，注册即送额度）",
            "准备运行环境：有电脑直接上手；没有电脑→申请无影云电脑（新用户免费 1 个月），选预装 Hermes 或 OpenClaw 的镜像就能直接用",
            "将 AI 工具对接到微信/飞书等日常平台，随时随地可用",
        ],
        "L2 入门": ["学习 AI 核心概念（过拟合、训练、推理等）", "掌握提示词工程", "用 AI 提效当前工作", "了解一个垂直方向的工具链"],
        "L3 进阶": ["系统学习数学基础（线性代数/概率论）", "学习 Python + 主流框架", "动手实践项目", "阅读经典论文"],
        "L4 专业": ["深入前沿方向论文", "参与开源项目", "独立完成研究/工程项目", "建立技术影响力"],
    }
    path = steps.get(level, steps["L2 入门"])

    if should == "建议学":
        reason = "建议系统性学习 AI，目标是实际应用"
    elif should == "信息不足，暂无法给出明确建议":
        reason = "你提供的信息不足以做出准确判断。建议先了解 AI 基础知识，等明确目标后再来做评估。"
    else:
        reason = "建议先以了解为主，不要急于投入"

    confidence = round(max(0.3, min(0.95, 0.85 - unknown_ratio * 0.55)), 2)

    ability_info = LEVEL_ABILITY.get(level, {})
    abil = ability_info.get("ability", "")
    sal = ability_info.get("salary", "")
    ability_line = f"**能做什么**：{abil}"
    if sal:
        ability_line += f"，{sal}"

    report = f"""## 评估结论

**建议**：{should}

**理由**：根据你的目标（{goal if goal and goal not in UNKNOWN else '未明确'}）、背景（{bg if bg and bg not in UNKNOWN else '未明确'}）和投入时间（{time_val if time_val and time_val not in UNKNOWN else '未明确'}），{reason}。

---

## 推荐水平

**{level}**

{ability_line}

---

## 推荐方向

**{direction_name}**

---

## 学习路径概要

"""
    for i, step in enumerate(path, 1):
        report += f"{i}. {step}\n"

    report += f"""
---

## 下一步行动

**{path[0] if path else '开始探索 AI'}**

---

## 信心指数

{confidence}
"""

    count_unknown = sum(1 for v in all_vals if v in UNKNOWN)
    report += f"\n\n本次评估基于你的回答生成，共答了{len(all_vals)}道题，其中{count_unknown}道选了'不知道'。选'不知道'越多，建议越保守。"

    if level in ("L3 进阶", "L4 专业") and bg and "计算机" not in bg:
        report += "\n---\n"
        report += "## 诚实提醒\n\n"
        report += "达到L3/L4水平需要长期投入，且不保证找到对口工作。\n"
        report += "学历和行业经验是就业门槛，AI技能是加分项。\n"
        report += "建议先从L2入门开始，在现有工作中找到AI应用场景，\n"
        report += "验证了价值再决定是否深入。\n"
    return report
