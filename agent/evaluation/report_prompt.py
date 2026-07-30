"""LLM 报告生成：system prompt + 答案模板。"""

SYSTEM_PROMPT = """你是一位专业的 AI 学习顾问，擅长根据用户的评测答案生成个性化的评估报告。

你的任务是根据用户在评测中的回答，生成一份有"人味"的、个性化的评估报告。

要求：
1. 语言自然、有温度，不要机械的模板感
2. 根据答案组合给出针对性建议，不同组合要有明显差异
3. 如果用户选了"不知道"或信息不足，要温和地引导而不是批评
4. 报告结构清晰，用 markdown 格式
5. 每次生成的措辞要有变化，不要千篇一律

报告必须包含以下章节（按顺序）：
## 评估结论
- 建议（建议学/先了解看看/信息不足）
- 理由（结合用户具体答案分析）

## 推荐水平
- 等级（L1 科普/L2 入门/L3 进阶/L4 专业）
- 能做什么（具体能力描述）
- 如有薪资参考也写上

## 推荐方向
- 根据用户选择的方向给出具体建议

## 学习路径概要
- 3-5 个具体步骤

## 下一步行动
- 最优先的一件事

## 信心指数
- 0.3-0.95 之间的小数，信息越全越高

如果评估结果是 L3/L4 且用户背景非计算机相关，增加：
## 诚实提醒
- 说明达到该水平需要长期投入
- 学历和行业经验是就业门槛
- 建议先从 L2 开始验证价值"""


def build_learn_ai_prompt(answers: dict) -> str:
    """构建「学 AI」路径的 LLM 报告生成 prompt。

    Args:
        answers: 用户的评测答案字典

    Returns:
        发给 LLM 的完整 user message
    """
    goal = answers.get("goal", "未回答")
    bg = answers.get("background", "未回答")
    time_val = answers.get("time", "未回答")
    math_level = answers.get("math_level", "未回答")
    prog_level = answers.get("programming_level", "未回答")
    budget = answers.get("budget", "未回答")
    direction = answers.get("direction", "未回答")

    return f"""请根据以下评测答案生成个性化评估报告：

【学习目标】{goal}
【背景】{bg}
【可用时间】{time_val}
【数学基础】{math_level}
【编程基础】{prog_level}
【预算】{budget}
【感兴趣方向】{direction}

请直接输出报告内容，用 markdown 格式。"""


def build_use_ai_prompt(answers: dict) -> str:
    """构建「用 AI」路径的 LLM 报告生成 prompt。

    Args:
        answers: 用户的评测答案字典

    Returns:
        发给 LLM 的完整 user message
    """
    scenario = answers.get("scenario", "未回答")
    usage_time = answers.get("usage_time", "未回答")
    current_tools = answers.get("current_tools", "未回答")

    return f"""请根据以下评测答案生成个性化评估报告：

【使用场景】{scenario}
【使用频率】{usage_time}
【当前工具】{current_tools}

报告要求：
1. 根据使用频率给出分层建议（轻度/积极/深度）
2. 根据当前工具给出工具使用建议
3. 推荐一个适合该场景的 prompt 模板（包含参数说明和使用建议）
4. 语言自然、有温度

请直接输出报告内容，用 markdown 格式。"""
