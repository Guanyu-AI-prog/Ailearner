import json
import time
from typing import Any, Dict, Optional

import httpx

from config import config
from agent.orchestrator import handle_message
from db import get_or_create_session, save_message, update_session


class FeishuBot:
    BASE_URL = "https://open.feishu.cn"

    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self._token: Optional[str] = None
        self._token_expire_at: float = 0

    async def _get_token(self) -> str:
        if self._token and time.time() < self._token_expire_at:
            return self._token
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.BASE_URL}/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": self.app_id, "app_secret": self.app_secret},
            )
            data = resp.json()
            self._token = data["tenant_access_token"]
            self._token_expire_at = time.time() + data.get("expire", 7200) - 120
        return self._token

    async def reply_message(self, message_id: str, text: str) -> Dict[str, Any]:
        token = await self._get_token()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.BASE_URL}/open-apis/im/v1/messages/{message_id}/reply",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "msg_type": "text",
                    "content": json.dumps({"text": text}, ensure_ascii=False),
                },
            )
            return resp.json()


_bot: Optional[FeishuBot] = None


def get_bot() -> Optional[FeishuBot]:
    global _bot
    if _bot is None and config.FEISHU_APP_ID and config.FEISHU_APP_SECRET:
        _bot = FeishuBot(config.FEISHU_APP_ID, config.FEISHU_APP_SECRET)
    return _bot


async def handle_event(body: dict) -> dict:
    if body.get("type") == "url_verify":
        return {"challenge": body["challenge"]}

    header = body.get("header", {})
    event_type = header.get("event_type", "")

    if event_type == "im.message.receive_v1":
        event = body.get("event", {})
        message = event.get("message", {})
        chat_type = message.get("chat_type", "")
        message_id = message.get("message_id", "")
        message_type = message.get("message_type", "")
        sender_id = event.get("sender", {}).get("sender_id", {})
        open_id = sender_id.get("open_id", "")

        if chat_type != "p2p" or message_type != "text":
            return {"code": 0}

        try:
            content = json.loads(message.get("content", "{}"))
            user_text = content.get("text", "").strip()
        except (json.JSONDecodeError, KeyError):
            return {"code": 0}

        if not user_text:
            return {"code": 0}

        bot = get_bot()
        if not bot:
            return {"code": 1, "msg": "Feishu bot not configured"}

        session_id = f"feishu_{open_id}"
        state = await get_or_create_session(session_id)

        initial_count = len(state.messages)
        full_response = ""
        async for chunk in handle_message(state, user_text, stream=False):
            if chunk["type"] == "content":
                full_response += chunk["text"]

        # Only save NEW messages (not all messages every time)
        for m in state.messages[initial_count:]:
            await save_message(session_id, m.role, m.content)
        await update_session(
            session_id,
            evaluation_started=state.evaluation_started,
            evaluation_done=state.evaluation_done,
            evaluation_phase=state.evaluation_phase,
            evaluation_report=state.evaluation_report,
            evaluation_path=state.evaluation_path,
            evaluation_answers=state.evaluation_answers,
        )

        if full_response:
            await bot.reply_message(message_id, full_response)

        return {"code": 0}

    return {"code": 0}
