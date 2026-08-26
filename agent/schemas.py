from pydantic import BaseModel, Field
from typing import Dict, List, Literal, Optional


class Message(BaseModel):
    role: str
    content: Optional[str] = None


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(..., min_length=1, max_length=2000)


class SessionState(BaseModel):
    session_id: str
    messages: List[Message] = []
    evaluation_answers: Dict[str, str] = {}
    evaluation_phase: int = 0
    evaluation_started: bool = False
    evaluation_done: bool = False
    evaluation_report: str = ""
    evaluation_path: str = ""


class StructuredAssessmentAnswer(BaseModel):
    question_id: str = Field(..., min_length=1, max_length=64)
    answer: Literal["A", "B", "C", "D"]


class StructuredAssessmentRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)
    answers: List[StructuredAssessmentAnswer] = Field(..., min_length=10, max_length=10)
