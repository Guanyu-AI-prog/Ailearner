"""评估报告生成：LLM 优先，规则兜底。"""

import asyncio
import logging
from typing import Dict, Optional

from config import config
from agent.schemas import SessionState
from agent.llm_client import ask_llm
from agent.evaluation.report_prompt import (
    SYSTEM_PROMPT,
    build_learn_ai_prompt,
    build_use_ai_prompt,
)

logger = logging.getLogger(__name__)

# LLM 超时配置（秒）
LLM_TIMEOUT = 5.0


# ─── 多维评分（纯规则，无 LLM 调用）─────────────────────────────────────

def _score_learning_fit(answers: Dict[str, str]) -> int:
    """学习适合度：goal + background + programming_level 的综合。"""
    goal = _resolve_answer(answers.get("goal", ""), config.LEARN_AI_QUESTIONS[0]["options"])
    bg = _resolve_answer(answers.get("background", ""), config.LEARN_AI_QUESTIONS[1]["options"])
    prog = _resolve_answer(answers.get("programming_level", ""), config.LEARN_AI_QUESTIONS[4]["options"])

    goal_scores = {"转行": 5, "学术研究": 5, "工作效率": 3, "纯粹好奇": 2, "先了解看看": 1}
    bg_scores = {"计算机": 5, "理工科": 4, "学生": 3, "文科": 2, "商科": 2, "艺术": 2, "其他": 1}
    prog_scores = {"丰富经验": 5, "会写基本": 4, "能看懂": 3, "零基础": 2}

    def _match_score(text: str, table: dict) -> int:
        for key, val in table.items():
            if key in text:
                return val
        return 2  # 默认中等偏低

    scores = [
        _match_score(goal, goal_scores),
        _match_score(bg, bg_scores),
        _match_score(prog, prog_scores),
    ]
    return round(sum(scores) / len(scores))


def _score_time_match(answers: Dict[str, str]) -> int:
    """时间投入匹配度：可用时间 vs 推荐学习时长。"""
    time_val = _resolve_answer(answers.get("time", ""), config.LEARN_AI_QUESTIONS[2]["options"])
    goal = _resolve_answer(answers.get("goal", ""), config.LEARN_AI_QUESTIONS[0]["options"])

    # 可用时间评分
    time_scores = {"10 小时以上": 5, "5-10 小时": 4, "2-5 小时": 3, "少于 2 小时": 1}
    time_score = 2
    for key, val in time_scores.items():
        if key in time_val:
            time_score = val
            break

    # 目标所需时间等级
    goal_time_need = {"转行": 5, "学术研究": 5, "工作效率": 3, "纯粹好奇": 2, "先了解看看": 2}
    need = 3
    for key, val in goal_time_need.items():
        if key in goal:
            need = val
            break

    # 匹配度：时间 >= 需求 → 高分，时间 < 需求 → 低分
    diff = time_score - need
    if diff >= 0:
        return min(5, 4 + diff)
    return max(1, 3 + diff)


def _score_budget_match(answers: Dict[str, str]) -> int:
    """预算匹配度：预算 vs 目标路径成本。"""
    budget = _resolve_answer(answers.get("budget", ""), config.LEARN_AI_QUESTIONS[5]["options"])
    goal = _resolve_answer(answers.get("goal", ""), config.LEARN_AI_QUESTIONS[0]["options"])

    budget_scores = {"预算充足": 5, "几千到上万": 4, "1000 元以内": 3, "零成本": 1}
    budget_score = 2
    for key, val in budget_scores.items():
        if key in budget:
            budget_score = val
            break

    # 目标所需预算等级
    goal_budget_need = {"学术研究": 5, "转行": 4, "工作效率": 2, "纯粹好奇": 1, "先了解看看": 1}
    need = 2
    for key, val in goal_budget_need.items():
        if key in goal:
            need = val
            break

    diff = budget_score - need
    if diff >= 0:
        return min(5, 4 + diff)
    return max(1, 3 + diff)


def _score_direction_clarity(answers: Dict[str, str]) -> int:
    """方向明确度：方向选择 + 目标清晰度。"""
    direction = _resolve_answer(answers.get("direction", ""), config.LEARN_AI_QUESTIONS[6]["options"])
    goal = _resolve_answer(answers.get("goal", ""), config.LEARN_AI_QUESTIONS[0]["options"])

    # 方向明确程度
    if not direction or "还没特定" in direction:
        dir_score = 1
    elif "全面了解" in direction:
        dir_score = 2
    else:
        dir_score = 5  # 有明确方向

    # 目标清晰度
    goal_scores = {"转行": 5, "学术研究": 5, "工作效率": 4, "纯粹好奇": 2, "先了解看看": 1}
    goal_score = 2
    for key, val in goal_scores.items():
        if key in goal:
            goal_score = val
            break

    return round((dir_score + goal_score) / 2)


def _score_use_ai(answers: Dict[str, str]) -> Dict[str, int]:
    """「用 AI」路径的评分：基于使用频率和工具经验。"""
    usage = answers.get("usage_time", "")
    tools = answers.get("current_tools", "")

    usage_scores = {"重度依赖": 5, "经常用": 4, "每天用一点": 3, "偶尔试一下": 1}
    usage_score = 2
    for key, val in usage_scores.items():
        if key in usage:
            usage_score = val
            break

    tool_scores = {"没用过": 1, "ChatGPT": 4, "文心一言": 3, "通义千问": 3, "Kimi": 3, "其他": 3}
    tool_score = 2
    for key, val in tool_scores.items():
        if key in tools:
            tool_score = val
            break

    # 用 AI 路径的维度含义不同：使用适合度、时间投入、工具熟练度、场景明确度
    return {
        "learning_fit": round((usage_score + tool_score) / 2),
        "time_match": usage_score,
        "budget_match": tool_score,
        "direction_clarity": 5 if answers.get("scenario") else 2,
    }


def calculate_scores(state: SessionState) -> Dict[str, int]:
    """计算多维评分（纯规则，无 LLM 调用）。返回各维度得分。"""
    if state.evaluation_path == "use":
        return _score_use_ai(state.evaluation_answers)

    return {
        "learning_fit": _score_learning_fit(state.evaluation_answers),
        "time_match": _score_time_match(state.evaluation_answers),
        "budget_match": _score_budget_match(state.evaluation_answers),
        "direction_clarity": _score_direction_clarity(state.evaluation_answers),
    }


def render_strengths_weaknesses(scores: Dict[str, int]) -> str:
    """根据评分生成「优势/短板」分析段落。"""
    if not scores:
        return ""

    dims = config.SCORING_DIMENSIONS
    sorted_dims = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    strengths = [k for k, v in sorted_dims if v >= 4]
    weaknesses = [k for k, v in sorted_dims if v <= 2]
    mid = [k for k, v in sorted_dims if 2 < v < 4]

    lines = ["## 优势与短板\n"]

    if strengths:
        names = "、".join(dims[k]["name"] for k in strengths)
        top_score = scores[strengths[0]]
        lines.append(f"**你的优势**：{names}（{top_score}/5 分）。这几项得分较高，说明你在这方面条件不错，可以作为学习的基础。\n")

    if weaknesses:
        names = "、".join(dims[k]["name"] for k in weaknesses)
        low_score = scores[weaknesses[0]]
        lines.append(f"**需要关注**：{names}（{low_score}/5 分）。这几项是你的短板，建议优先改善或选择不需要这些条件的学习路径。\n")

    if mid:
        names = "、".join(dims[k]["name"] for k in mid)
        lines.append(f"**尚可提升**：{names}。还有提升空间，可以在学习过程中逐步改善。\n")

    if not strengths and not weaknesses:
        lines.append("你的各项条件比较均衡，没有明显的强项或短板。\n")

    return "\n".join(lines)


async def _call_llm_with_timeout(prompt: str, timeout: float = LLM_TIMEOUT) -> Optional[str]:
    """调用 LLM 生成报告，超时返回 None。"""
    try:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        result = await asyncio.wait_for(ask_llm(messages), timeout=timeout)
        return result
    except asyncio.TimeoutError:
        logger.warning("LLM 报告生成超时（%.1fs），将使用规则版报告", timeout)
        return None
    except Exception as e:
        logger.warning("LLM 报告生成失败: %s，将使用规则版报告", e)
        return None


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


def _resolve_answer(answer: str, options: list) -> str:
    """将存储的答案（可能是数字）解析为完整选项文本。"""
    if not answer:
        return ""
    from agent.evaluation.state_machine import _match_option
    matched = _match_option(answer, options)
    return matched or answer


def _render_prompt_template(scenario: dict) -> str:
    """渲染 prompt 模板。"""
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


def _render_rule_based_use_ai_report(state: SessionState) -> str:
    """规则版「用 AI」报告（原 render_use_ai_report 逻辑，作为 LLM 兜底）。"""
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


async def render_use_ai_report(state: SessionState) -> str:
    """生成「用 AI」路径的评估报告（LLM 优先，规则兜底）。"""
    # 计算多维评分
    state.evaluation_scores = calculate_scores(state)
    sw_section = render_strengths_weaknesses(state.evaluation_scores)

    prompt = build_use_ai_prompt(state.evaluation_answers)
    llm_report = await _call_llm_with_timeout(prompt)
    if llm_report:
        return llm_report + "\n\n" + sw_section
    return _render_rule_based_use_ai_report(state) + "\n\n" + sw_section


def _generate_rule_based_report(state: SessionState) -> str:
    """规则版「学 AI」报告（原 generate_report 逻辑，作为 LLM 兜底）。"""
    answers = state.evaluation_answers

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


async def generate_report(state: SessionState) -> str:
    """生成「学 AI」路径的评估报告（LLM 优先，规则兜底）。"""
    # 计算多维评分
    state.evaluation_scores = calculate_scores(state)
    sw_section = render_strengths_weaknesses(state.evaluation_scores)

    prompt = build_learn_ai_prompt(state.evaluation_answers)
    llm_report = await _call_llm_with_timeout(prompt)
    if llm_report:
        return llm_report + "\n\n" + sw_section
    return _generate_rule_based_report(state) + "\n\n" + sw_section
