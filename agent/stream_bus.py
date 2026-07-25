"""轻量事件总线：统一 SSE 输出格式。"""

import asyncio
from typing import AsyncIterator, Optional


class StreamBus:
    """进程内事件总线，用于统一 SSE 输出。"""

    def __init__(self):
        self._queue: asyncio.Queue[Optional[dict]] = asyncio.Queue()

    async def emit(self, event_type: str, data: dict = None):
        """发送事件。"""
        event = {"type": event_type}
        if data:
            event.update(data)
        await self._queue.put(event)

    async def emit_content(self, text: str):
        """发送内容片段（最常用）。"""
        await self.emit("content", {"text": text})

    async def emit_status(self, text: str):
        """发送状态事件。"""
        await self.emit("status", {"text": text})

    async def emit_done(self):
        """发送完成信号并关闭队列。"""
        await self._queue.put(None)

    async def events(self) -> AsyncIterator[dict]:
        """迭代所有事件，直到 done。"""
        while True:
            event = await self._queue.get()
            if event is None:
                break
            yield event
