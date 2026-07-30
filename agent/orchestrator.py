"""消息路由：决定由哪个模块处理用户消息。"""

from agent.schemas import Message, SessionState
from agent.core import normal_chat
from agent.evaluation.state_machine import (
    is_evaluation_in_progress,
    should_start_evaluation,
    start_evaluation,
    continue_evaluation,
)


async def handle_message(state: SessionState, message: str, stream: bool = True):
    """统一分发入口，返回 async generator。"""
    if state.evaluation_done:
        gen = normal_chat(state, message, stream)
    elif is_evaluation_in_progress(state):
        gen = continue_evaluation(state, message, stream)
    elif should_start_evaluation(message):
        gen = start_evaluation(state, stream)
    else:
        gen = normal_chat(state, message, stream)
    async for chunk in gen:
        yield chunk
