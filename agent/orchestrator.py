"""消息路由：决定由哪个模块处理用户消息。"""

from agent.schemas import Message, SessionState
from agent.core import normal_chat
from agent.evaluation.state_machine import (
    EXPLICIT_EVAL,
    is_evaluation_in_progress,
    looks_like_question,
    should_start_evaluation,
    start_evaluation,
    continue_evaluation_with_fallback,
)

# 主动退出评估
EXIT_WORDS = ("跳过", "退出", "不评估了", "不做了", "算了")


def _stop_evaluation(state: SessionState) -> None:
    """重置评估状态，交回普通对话。"""
    state.evaluation_started = False
    state.evaluation_phase = 0
    state.evaluation_path = ""
    state.evaluation_answers = {}


async def _normal_chat_with_eval_hint(state: SessionState, message: str, stream: bool = True):
    """回答提问后软引导一次评估（不强制）。"""
    async for chunk in normal_chat(state, message, stream):
        yield chunk
    hint = "\n\n---\n想让我帮你判断方向的话，回「帮我评估」，我问你几个问题就行。"
    state.messages.append(Message(role="assistant", content=hint))
    yield {"type": "content", "text": hint}


async def handle_message(state: SessionState, message: str, stream: bool = True):
    """统一分发入口，返回 async generator。

    优先级：退出词 > 评估已完成 > 评估进行中(带逃生阀) > 显式评估请求
            > 触发词(且非问句) > 普通对话
    """
    if any(w in message for w in EXIT_WORDS):
        _stop_evaluation(state)
        gen = normal_chat(state, message, stream)
    elif state.evaluation_done:
        gen = normal_chat(state, message, stream)
    elif is_evaluation_in_progress(state):
        gen = continue_evaluation_with_fallback(state, message, stream)
    elif any(t in message for t in EXPLICIT_EVAL):
        gen = start_evaluation(state, stream)
    elif should_start_evaluation(message) and looks_like_question(message):
        gen = _normal_chat_with_eval_hint(state, message, stream)
    elif should_start_evaluation(message):
        gen = start_evaluation(state, stream)
    else:
        gen = normal_chat(state, message, stream)
    async for chunk in gen:
        yield chunk
