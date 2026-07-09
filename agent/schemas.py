from pydantic import BaseModel
from typing import Dict, List


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    session_id: str
    message: str


class SessionState(BaseModel):
    session_id: str
    messages: List[Message] = []
    evaluation_answers: Dict[str, str] = {}
    evaluation_phase: int = 0
    evaluation_started: bool = False
    evaluation_done: bool = False
    evaluation_report: str = ""
    evaluation_path: str = ""
