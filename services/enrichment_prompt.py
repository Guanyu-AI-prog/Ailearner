"""报告个人化改写的 prompt 构造。

硬约束（写进 system prompt 并由 report_enricher 校验兜底）：
- 不改任何数字、分数、等级、profile
- 只输出 JSON，结构与输入一致
- 文字要求：贴着答卷说人话，不用空话套话
"""

import json
from typing import Any
from config.assessment import ASSESSMENT_QUESTIONS, DIMENSION_NAMES

_SYSTEM_PROMPT = """你是一位懂 AI 学习领域的资深学习顾问。用户刚完成一份 AI 学习能力测评，你会收到：
1. 一份系统已生成的标准化报告（JSON）。
2. 这位学习者的全部问卷答案文本。

你的任务：把报告中的文字改写得更贴合这位具体学习者，像一位了解他情况的顾问 personalized 说话。

硬性规则（违反即整体作废）：
1. 只允许改写这些文字字段的"内容"：positioning，short_term_plan 数组，learning_path 数组，pitfalls 数组，每个 dimension 里的 analysis。
2. overall_score、level、profile、dimensions 的 id 和 score、顶层字段名集合，逐字保持不变。
3. 不允许出现任何新数字（分数、天数、课程数量等），禁止写"预计X天学会"这类量化承诺。
4. positioning ≤ 60字；每个 analysis ≤ 120字；每个列表保持原有条数。
5. 分析必须引用他问卷答案里的具体信息（如"你提到每天只有30分钟"），不许用只看分数就会写出的通用话术。
6. 语言：简体中文，直接、务实、不说"建议你保持良好心态"这种废话；可以温和但不能空。
7. 只输出 JSON 本身，不要 markdown 代码块，不要解释。"""


def _answer_lines(answers: dict[str, str]) -> str:
    lines = []
    for question in ASSESSMENT_QUESTIONS:
        answer_text = answers.get(question["id"], "")
        lines.append(f"- {question['question']}：{answer_text}")
    return "\n".join(lines)


def build_rewrite_prompt(report: dict[str, Any], answers: dict[str, str]) -> list[dict[str, str]]:
    """构造改写用的 messages：system 规则 + user(报告+答案)。"""
    user_content = (
        "【问卷答案】\n"
        f"{_answer_lines(answers)}\n\n"
        "【待改写的报告 JSON】\n"
        f"{json.dumps(report, ensure_ascii=False)}"
    )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
