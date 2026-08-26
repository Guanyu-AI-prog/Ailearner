"""Structured assessment question bank and scoring metadata."""

from typing import Final, TypedDict


class AssessmentOption(TypedDict):
    key: str
    text: str


class AssessmentQuestion(TypedDict):
    id: str
    dimension: str
    question: str
    options: list[AssessmentOption]


DIMENSION_NAMES: Final[dict[str, str]] = {
    "programming": "编程基础功底",
    "ai_experience": "AI 工具使用经验",
    "time_commitment": "每日可投入学习时长",
    "learning_goals": "个人学习目标与发展方向",
}


ASSESSMENT_QUESTIONS: Final[list[AssessmentQuestion]] = [
    {
        "id": "programming_level",
        "dimension": "programming",
        "question": "你的编程基础水平？",
        "options": [
            {"key": "A", "text": "完全零基础，无任何代码经验"},
            {"key": "B", "text": "了解基础概念，未独立写过代码"},
            {"key": "C", "text": "能编写简单脚本，入门 Python 基础"},
            {"key": "D", "text": "具备独立开发小型项目能力"},
        ],
    },
    {
        "id": "ai_tool_experience",
        "dimension": "ai_experience",
        "question": "你对 AI 大模型 / Agent 工具的熟悉程度？",
        "options": [
            {"key": "A", "text": "从未接触过"},
            {"key": "B", "text": "仅日常聊天使用"},
            {"key": "C", "text": "会使用 AI 工具辅助工作 / 学习"},
            {"key": "D", "text": "了解 Agent、RAG 等技术概念"},
        ],
    },
    {
        "id": "daily_study_time",
        "dimension": "time_commitment",
        "question": "你每日可稳定投入 AI 学习的时长？",
        "options": [
            {"key": "A", "text": "30 分钟以内"},
            {"key": "B", "text": "30 分钟 - 1 小时"},
            {"key": "C", "text": "1-2 小时"},
            {"key": "D", "text": "2 小时以上"},
        ],
    },
    {
        "id": "core_goal",
        "dimension": "learning_goals",
        "question": "你的核心学习目标？",
        "options": [
            {"key": "A", "text": "零基础入门，掌握 AI 基础应用"},
            {"key": "B", "text": "提升技能，用于副业实操"},
            {"key": "C", "text": "系统学习，转行 AI 技术岗位"},
            {"key": "D", "text": "自我提升，拓展技术认知"},
        ],
    },
    {
        "id": "learning_duration",
        "dimension": "ai_experience",
        "question": "你接触 AI 学习的时长？",
        "options": [
            {"key": "A", "text": "刚起步学习"},
            {"key": "B", "text": "1-3 个月"},
            {"key": "C", "text": "3-6 个月"},
            {"key": "D", "text": "6 个月以上"},
        ],
    },
    {
        "id": "priority_direction",
        "dimension": "learning_goals",
        "question": "你最想优先学习的方向？",
        "options": [
            {"key": "A", "text": "AI 日常办公提效"},
            {"key": "B", "text": "RAG 知识库落地应用"},
            {"key": "C", "text": "Agent 智能体开发"},
            {"key": "D", "text": "全链路 AI 项目实战"},
        ],
    },
    {
        "id": "self_learning_ability",
        "dimension": "learning_goals",
        "question": "你的逻辑思维与自主学习能力自评？",
        "options": [
            {"key": "A", "text": "较弱，需要手把手教程"},
            {"key": "B", "text": "一般，跟随教程可完成学习"},
            {"key": "C", "text": "良好，可自主摸索实操"},
            {"key": "D", "text": "优秀，可独立拆解项目问题"},
        ],
    },
    {
        "id": "technical_experience",
        "dimension": "learning_goals",
        "question": "你是否有互联网 / 技术相关从业经验？",
        "options": [
            {"key": "A", "text": "无任何相关经验"},
            {"key": "B", "text": "非技术岗位，略有接触"},
            {"key": "C", "text": "基础技术岗位经验"},
            {"key": "D", "text": "完整技术岗位工作经验"},
        ],
    },
    {
        "id": "learning_motivation",
        "dimension": "learning_goals",
        "question": "你学习 AI 的核心驱动力？",
        "options": [
            {"key": "A", "text": "兴趣爱好，自主提升"},
            {"key": "B", "text": "工作需要，提升效率"},
            {"key": "C", "text": "职业转型，刚需进阶"},
            {"key": "D", "text": "副业增收，技能变现"},
        ],
    },
    {
        "id": "preferred_mode",
        "dimension": "learning_goals",
        "question": "你偏好的学习模式？",
        "options": [
            {"key": "A", "text": "图文教程 + 案例实操"},
            {"key": "B", "text": "视频系统化教学"},
            {"key": "C", "text": "项目驱动，边做边学"},
            {"key": "D", "text": "问题驱动，针对性查漏补缺"},
        ],
    },
]
