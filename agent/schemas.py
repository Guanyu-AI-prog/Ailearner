from pydantic import BaseModel, Field
from typing import Dict, List, Optional


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
