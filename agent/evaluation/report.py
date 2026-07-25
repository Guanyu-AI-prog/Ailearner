"""评估报告生成：纯函数，不依赖外部状态。"""

from config import config
from agent.schemas import SessionState


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


def render_use_ai_report(state: SessionState) -> str:
    """生成「用 AI」路径的评估报告。"""
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


def generate_report(state: SessionState) -> str:
    """生成「学 AI」路径的评估报告。"""
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
