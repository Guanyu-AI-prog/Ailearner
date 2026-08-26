"""Deterministic structured-assessment scoring and report generation."""

from collections import defaultdict
from typing import Final

from config.assessment import ASSESSMENT_QUESTIONS, DIMENSION_NAMES


_ANSWER_SCORES: Final[dict[str, int]] = {"A": 25, "B": 50, "C": 75, "D": 100}


def _answer_text(question_id: str, answer: str) -> str:
    """Return the display text for one validated answer."""
    for question in ASSESSMENT_QUESTIONS:
        if question["id"] == question_id:
            for option in question["options"]:
                if option["key"] == answer:
                    return option["text"]
    return answer


def _dimension_scores(answers: dict[str, str]) -> dict[str, int]:
    """Calculate the normalized score for each assessment dimension."""
    scores: dict[str, list[int]] = defaultdict(list)
    for question in ASSESSMENT_QUESTIONS:
        answer = answers[question["id"]]
        scores[question["dimension"]].append(_ANSWER_SCORES[answer])
    return {
        dimension: round(sum(values) / len(values))
        for dimension, values in scores.items()
    }


def _level_for_score(overall_score: int) -> tuple[str, str]:
    """Map an overall score to a clear learner level."""
    if overall_score < 45:
        return "零基础", "先建立 AI 基础认知与稳定的学习习惯。"
    if overall_score < 65:
        return "入门", "已经具备起步条件，适合通过案例和工具建立能力。"
    if overall_score < 80:
        return "进阶", "可用项目驱动学习，逐步形成可复用的 AI 应用能力。"
    return "进阶", "基础较扎实，适合挑战完整 AI 应用项目并持续深化。"


def _dimension_feedback(dimension: str, score: int) -> str:
    """Create concise, actionable feedback for one dimension."""
    name = DIMENSION_NAMES[dimension]
    if score < 50:
        return f"{name}仍处于起步阶段，建议先完成低门槛练习并建立正反馈。"
    if score < 75:
        return f"{name}具备基础，下一步应通过固定节奏和真实案例巩固。"
    return f"{name}表现较好，可将学习重心转向实战和成果沉淀。"


def _learning_plan(answers: dict[str, str], level: str) -> tuple[list[str], list[str], list[str]]:
    """Build plans that reflect level, preferred direction, and available time."""
    direction = answers["priority_direction"]
    direction_steps = {
        "A": ["选择一个日常办公场景，连续一周用 AI 完成真实任务", "沉淀 3 个可复用 Prompt 模板"],
        "B": ["完成一个小型知识库问答原型", "学习文档切分、检索与回答质量评估"],
        "C": ["用一个 Agent 框架完成工具调用练习", "为 Agent 增加可观测日志和异常处理"],
        "D": ["选择一个完整业务问题拆解需求、数据和交付物", "发布可演示的端到端 AI 项目"],
    }
    foundation = ["明确一个可量化的学习目标", "每周复盘一次学习产出并调整计划"]
    level_step = "完成 2 个小型案例" if level in {"零基础", "入门"} else "完成 1 个可公开展示的项目"
    short_term = [foundation[0], level_step, foundation[1]]
    learning_path = direction_steps[direction] + ["将成果整理为作品说明或学习笔记"]
    pitfalls = ["不要同时追逐过多工具，优先完成一个方向的闭环", "避免只看教程不动手，每次学习都要留下可验证产出"]
    if answers["daily_study_time"] in {"A", "B"}:
        pitfalls.append("时间有限时采用 30 分钟任务卡，避免制定无法持续的大计划")
    return short_term, learning_path, pitfalls


def generate_assessment_report(answers: dict[str, str]) -> dict[str, object]:
    """Generate a stable, structured report from the fixed question bank."""
    dimension_scores = _dimension_scores(answers)
    overall_score = round(sum(dimension_scores.values()) / len(dimension_scores))
    level, positioning = _level_for_score(overall_score)
    short_term, learning_path, pitfalls = _learning_plan(answers, level)
    dimensions = [
        {
            "id": dimension,
            "name": DIMENSION_NAMES[dimension],
            "score": score,
            "analysis": _dimension_feedback(dimension, score),
        }
        for dimension, score in dimension_scores.items()
    ]
    profile = {
        question["question"]: _answer_text(question["id"], answers[question["id"]])
        for question in ASSESSMENT_QUESTIONS
    }
    return {
        "overall_score": overall_score,
        "level": level,
        "positioning": positioning,
        "dimensions": dimensions,
        "short_term_plan": short_term,
        "learning_path": learning_path,
        "pitfalls": pitfalls,
        "profile": profile,
    }
