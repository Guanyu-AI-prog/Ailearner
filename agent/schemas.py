from pydantic import BaseModel, Field
from typing import Dict, List, Optional


class EvaluationResult(BaseModel):
    should_learn: bool
    reason: str
    target_level: str = Field(description="L1科普/L2入门/L3进阶/L4专业")
    recommended_direction: str
    confidence: float = Field(ge=0, le=1)
    learning_path_summary: str
    next_action: str


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    session_id: str
    reply: str


class SessionState(BaseModel):
    session_id: str
    messages: List[Message] = []
    evaluation_answers: Dict[str, str] = {}
    evaluation_phase: int = 0
    evaluation_started: bool = False
    evaluation_done: bool = False
    evaluation_report: str = ""
    evaluation_path: str = ""


class ToolCall(BaseModel):
    name: str
    arguments: str


class LLMResponse(BaseModel):
    content: str = ""
    tool_calls: List[ToolCall] = []
