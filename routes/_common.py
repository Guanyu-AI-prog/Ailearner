"""路由模块共享函数 — 提取自 routes/chat.py"""

from db import save_message, update_session


async def save_state(state, initial_count):
    """保存会话状态（新消息 + session 字段）"""
    for m in state.messages[initial_count:]:
        await save_message(state.session_id, m.role, m.content)
    await update_session(
        state.session_id,
        evaluation_started=state.evaluation_started,
        evaluation_done=state.evaluation_done,
        evaluation_phase=state.evaluation_phase,
        evaluation_report=state.evaluation_report,
        evaluation_path=state.evaluation_path,
        evaluation_answers=state.evaluation_answers,
    )