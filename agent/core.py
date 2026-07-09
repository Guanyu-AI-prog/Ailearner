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
                 "方向", "规划", "学习路径", "零基础", "该怎么学"]
    msg_lower = message.lower()
    for t in triggers:
        if t in msg_lower:
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
                tc_id = f"call_{tc['name']}"
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
    reply = f"## ? 入门评估\n\n很高兴你想了解 AI！我先问你几个问题，帮你判断最适合的方向。\n\n**{q['question']}**\n\n"
    for i, opt in enumerate(q["options"], 1):
        reply += f"{i}. {opt}\n"
    reply += "\n请直接回答或选择对应的数字告诉我 ~"
    state.messages.append(Message(role="assistant", content=reply))
    yield {"type": "content", "text": reply}


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
    return config.USE_AI_SCENARIOS[0], 0


async def continue_evaluation(state: SessionState, message: str, stream: bool = True):
    phase = state.evaluation_phase
    # phase == 0  means they just answered the very first question (学 vs 用)
    if phase == 0:
        ans = message.strip()
        is_use = ("用" in ans and "学" not in ans) or "工具" in ans or "效率" in ans
        state.evaluation_path = "use" if is_use else "learn"
        state.evaluation_answers["path"] = ans
        state.evaluation_phase = 1

        if state.evaluation_path == "use":
            reply = "## ? 用 AI 场景选择\n\n你在什么场景需要 AI 帮忙？选一个，我直接给你现成的 prompt 模板：\n\n"
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

    # ---- "用 AI" path: phase >= 1, scenario just chosen ----
    if state.evaluation_path == "use":
        state.evaluation_done = True
        scenario, _ = _match_scenario(message)
        state.evaluation_answers["scenario"] = scenario["name"]
        report = _render_prompt_template(scenario)
        state.evaluation_report = report
        state.messages.append(Message(role="assistant", content=report))
        yield {"type": "content", "text": report}
        return

    # ---- "学 AI" path: phase >= 1, cycling through LEARN_AI_QUESTIONS ----
    q_idx = phase - 1  # map to LEARN_AI_QUESTIONS index
    current_q = config.LEARN_AI_QUESTIONS[q_idx]
    state.evaluation_answers[current_q["id"]] = message

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
    return f"""## ✅ 你的专属 Prompt 模板

### ? 场景：{scenario['name']}

复制以下模板，把用 `{{}}` 标记的参数替换成你的内容就行：

---

```markdown
{scenario['prompt']}
```

---

### ? 参数说明

{params_text}

---

### ? 使用建议

{scenario['advice']}

---

? **提示**：把这个模板收藏起来，每次用到直接复制，填上具体内容就能用。
"""


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
    "提升工作效率": "L2 入门",
    "学术研究": "L4 专业",
    "纯粹好奇": "L1 科普",
    "先了解看看": "L1 科普",
}

async def generate_report(state: SessionState) -> str:
    answers = state.evaluation_answers
    goal = answers.get("goal", "")
    bg = answers.get("background", "")
    time_val = answers.get("time", "")
    math_lev = answers.get("math_level", "")
    prog_lev = answers.get("programming_level", "")
    budget = answers.get("budget", "")
    direction = answers.get("direction", "")

    direction_name = DIRECTION_MAP.get(direction, "通用入门")
    level = LEVEL_MAP.get(goal, "L2 入门")

    if math_lev in ("高中数学水平", "对数学没信心") and level in ("L3", "L4"):
        level = "L2 入门"
    if prog_lev in ("零基础", "能看懂一些") and level in ("L3", "L4"):
        level = "L2 入门"
    if time_val in ("少于 2 小时",):
        level = "L1 科普"
    if budget == "零成本":
        level = "L2 入门"

    should = "建议学" if goal not in ("还没想清楚", "纯粹好奇") else "先了解看看，不建议盲目投入"

    steps = {
        "L1 科普": [
            "使用 Agent 型 AI（如 Dify / OpenClaw），比对话式聊天更能理解 AI 的能力边界",
            "申请第一个 API Key（推荐小米 MiMo 开放平台，注册即送额度）",
            "准备运行环境：有电脑直接上手；没有电脑→申请无影云电脑（新用户免费 1 个月），选预装 Hermes 或 OpenClaw 的镜像就能直接用",
            "将 AI 工具对接到微信/飞书等日常平台，随时随地可用",
        ],
        "L2 入门": ["学习 AI 核心概念（过拟合、训练、推理等）", "掌握提示词工程", "用 AI 提效当前工作", "了解一个垂直方向的工具链"],
        "L3 进阶": ["系统学习数学基础（线性代数/概率论）", "学习 Python + 主流框架", "动手实践项目", "阅读经典论文"],
        "L4 专业": ["深入前沿方向论文", "参与开源项目", "独立完成研究/工程项目", "建立技术影响力"],
    }
    path = steps.get(level, steps["L2 入门"])

    report = f"""## ? 评估结论

**建议**：{should}

**理由**：根据你的目标（{goal}）、背景（{bg}）和投入时间（{time_val}），{'建议系统性学习 AI，目标是实际应用' if should == '建议学' else '建议先以了解为主，不要急于投入'}。

---

## ? 推荐水平

**{level}**

---

## ? 推荐方向

**{direction_name}**

---

## ? 学习路径概要

"""
    for i, step in enumerate(path, 1):
        report += f"{i}. {step}\n"

    report += f"""
---

## ? 下一步行动

**{path[0] if path else '开始探索 AI'}**

---

## ? 信心指数

0.85
"""

    if level in ("L3 进阶", "L4 专业") and bg != "计算机/IT 相关":
        report += "\n---\n"
        report += "## ⚠️ 诚实提醒\n\n"
        report += "达到L3/L4水平需要长期投入，且不保证找到对口工作。\n"
        report += "学历和行业经验是就业门槛，AI技能是加分项。\n"
        report += "建议先从L2入门开始，在现有工作中找到AI应用场景，\n"
        report += "验证了价值再决定是否深入。\n"
    return report
