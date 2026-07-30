# AILearner 架构改进方案 — 借鉴 DeepTutor

> **来源**: 对 DeepTutor v1.5.3 和 AILearner 两个项目的深度审查
> **日期**: 2026-07-25
> **核心思想**: 借鉴 DeepTutor 的分层设计，但保持 AILearner 的轻量风格。每层只需几十行代码，让系统从"能跑"变成"能维护"。

---

## 目录

1. [架构拆分：core.py → 多模块](#1-架构拆分corepy--多模块)
2. [工具协议：ABC 抽象注册](#2-工具协议abc-抽象注册)
3. [LLM 调用：重试 + 超时 + 熔断](#3-llm-调用重试--超时--熔断)
4. [事件总线：统一 SSE 输出](#4-事件总线统一-sse-输出)
5. [会话管理：SessionStore 抽象](#5-会话管理sessionstore-抽象)
6. [认证中间件：轻量可开关](#6-认证中间件轻量可开关)
7. [配置管理：分离关注点](#7-配置管理分离关注点)
8. [消息截断：上下文窗口控制](#8-消息截断上下文窗口控制)
9. [测试体系：从 0 到基础覆盖](#9-测试体系从-0-到基础覆盖)
10. [Docker 改进](#10-docker-改进)
11. [实施路线图](#11-实施路线图)

---

## 1. 架构拆分：core.py → 多模块

### DeepTutor 做法

```
runtime/
  orchestrator.py      # 路由分发（~200行）
  registry/            # 工具/能力注册表
capabilities/          # 多阶段能力管道
tools/                 # 单函数工具
services/              # LLM、DB、存储等服务
```

orchestrator 只负责"谁来处理这条消息"，具体逻辑分散到各模块。

### AILearner 现状

`agent/core.py` 588 行，7 个职责揉在一起：

| 职责 | 行数 | 说明 |
|------|------|------|
| LLM 客户端管理 | 11-34 | 单例客户端 + `ask_llm()` |
| 流式响应组装 | 37-59 | `generate_stream()` + tool call 缓冲 |
| 意图路由 | 62-106 | `should_start_evaluation()`, `handle_message()` |
| 普通对话 + 工具 | 117-176 | `normal_chat()` — 构建消息、处理 tool call |
| 评估流程 | 179-329 | `start_evaluation()`, `continue_evaluation()` |
| 报告生成 | 436-587 | `generate_report()` + 渲染函数 |
| 选项匹配 | 109-220 | `_resolve_answer()`, `_match_option()` |

### 改进方案

```
agent/
  __init__.py
  orchestrator.py        # 消息路由 + 意图判断（~80行）
  llm_client.py          # LLM 调用 + 重试 + 超时（~60行）
  evaluation/
    __init__.py
    state_machine.py     # 评估状态机 + 问题驱动（~150行）
    report.py            # 报告生成（~150行，纯函数）
  tools.py               # 工具定义（保持现状或升级为协议）
  schemas.py             # 数据模型（保持）
  prompts.py             # System prompt（保持）
  feishu.py              # 飞书集成（保持）
```

**`agent/orchestrator.py`** — 纯路由，不含业务逻辑：

```python
"""消息路由：决定由哪个模块处理用户消息。"""

from agent.evaluation.state_machine import (
    is_evaluation_in_progress,
    start_evaluation,
    continue_evaluation,
)
from agent.llm_client import normal_chat
from agent.schemas import SessionState


async def handle_message(state: SessionState, user_text: str):
    """统一分发入口，返回 async generator。"""
    if is_evaluation_in_progress(state):
        async for event in continue_evaluation(state, user_text):
            yield event
    elif should_start_evaluation(user_text):
        async for event in start_evaluation(state):
            yield event
    else:
        async for event in normal_chat(state, user_text):
            yield event
```

**收益**:
- 每个文件 < 200 行，职责单一
- 修改评估逻辑不影响对话功能
- 可独立测试每个模块

---

## 2. 工具协议：ABC 抽象注册

### DeepTutor 做法

```python
# core/tool_protocol.py
class BaseTool(ABC):
    @abstractmethod
    def get_definition(self) -> dict:
        """返回 OpenAI function calling JSON Schema。"""
        ...

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """执行工具，返回结果。"""
        ...
```

工具通过注册表自动发现，LLM 通过 schema 自动调用。新增工具只需实现两个方法，注册到表中即可。

### AILearner 现状

```python
# agent/tools.py
TOOLS = [
    {"type": "function", "function": {"name": "search_web", ...}},
    {"type": "function", "function": {"name": "recommend_cloud_computer", ...}},
    {"type": "function", "function": {"name": "generate_learning_path", ...}},
]

async def execute_tool(name: str, arguments: dict) -> str:
    if name == "search_web":
        return await search_web(arguments["query"])
    elif name == "recommend_cloud_computer":
        return recommend_cloud_computer(arguments["budget"])
    elif name == "generate_learning_path":
        return generate_learning_path(arguments["goal"], arguments.get("level"))
    else:
        return f"未知工具: {name}"
```

新增工具需改两处：`TOOLS` 列表 + `execute_tool` 的 if/elif。

### 改进方案

```python
# agent/tools/base.py
from abc import ABC, abstractmethod


class BaseTool(ABC):
    """工具基类：实现 get_definition() 和 execute() 即可注册。"""

    @abstractmethod
    def get_definition(self) -> dict:
        """返回 OpenAI function calling 格式的工具定义。"""
        ...

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """执行工具，返回字符串结果。"""
        ...


# agent/tools/registry.py
from typing import Dict
from agent.tools.base import BaseTool

_registry: Dict[str, BaseTool] = {}


def register(tool: BaseTool):
    """注册工具到全局注册表。"""
    name = tool.get_definition()["function"]["name"]
    _registry[name] = tool


def get_definitions() -> list:
    """返回所有工具的 JSON Schema 定义，用于 LLM 调用。"""
    return [t.get_definition() for t in _registry.values()]


async def execute(name: str, arguments: dict) -> str:
    """按名称执行工具。"""
    tool = _registry.get(name)
    if not tool:
        return f"未知工具: {name}"
    try:
        return await tool.execute(**arguments)
    except Exception as e:
        return f"工具执行出错: {e}"


# agent/tools/web_search.py
from agent.tools.base import BaseTool


class WebSearchTool(BaseTool):
    def get_definition(self):
        return {
            "type": "function",
            "function": {
                "name": "search_web",
                "description": "搜索互联网获取最新信息",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词"}
                    },
                    "required": ["query"],
                },
            },
        }

    async def execute(self, query: str, **kwargs) -> str:
        # ... 现有 search_web 逻辑 ...
        pass


# agent/tools/__init__.py — 启动时注册所有工具
from agent.tools.registry import register
from agent.tools.web_search import WebSearchTool
from agent.tools.cloud_computer import CloudComputerTool
from agent.tools.learning_path import LearningPathTool

register(WebSearchTool())
register(CloudComputerTool())
register(LearningPathTool())
```

**收益**:
- 新增工具只需创建一个文件 + 在 `__init__.py` 加一行 `register()`
- 工具定义和实现在同一文件，不会遗漏
- 类型检查器可验证工具实现是否完整

---

## 3. LLM 调用：重试 + 超时 + 熔断

### DeepTutor 做法

- `services/llm/traffic_control.py` — 令牌桶限流
- `provider_core/base.py` — 指数退避重试
- 区分瞬态错误（429/502/503）和永久错误（401/400）
- 多 Provider 可切换（OpenAI/Anthropic/DashScope）

### AILearner 现状

```python
# agent/core.py:24-34
async def ask_llm(messages: list, model: str = None) -> str:
    client = get_client()
    model = model or config.LLM_MODEL
    response = await client.chat.completions.create(
        model=model, messages=messages
    )
    return response.choices[0].message.content
```

零容错。API 限流、超时、500 直接抛异常，用户看到原始错误。

### 改进方案

```python
# agent/llm_client.py
"""LLM 客户端：封装调用、重试、超时、错误处理。"""

import asyncio
import logging
from typing import AsyncIterator, Optional

from openai import AsyncOpenAI, APITimeoutError, RateLimitError, APIStatusError
import config

logger = logging.getLogger(__name__)

_client: Optional[AsyncOpenAI] = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = config.get_api_key()
        _client = AsyncOpenAI(
            api_key=api_key,
            base_url=config.LLM_BASE_URL,
            timeout=30.0,  # 明确超时，而非默认 600s
        )
    return _client


async def ask_llm(messages: list, model: str = None, max_retries: int = 3) -> str:
    """调用 LLM，自动重试瞬态错误。"""
    client = get_client()
    model = model or config.LLM_MODEL

    for attempt in range(max_retries):
        try:
            response = await client.chat.completions.create(
                model=model, messages=messages
            )
            content = response.choices[0].message.content
            if not content:
                raise ValueError("LLM 返回空内容")
            return content

        except RateLimitError:
            wait = 2 ** attempt
            logger.warning(f"LLM 限流，{wait}s 后重试 (attempt {attempt+1})")
            await asyncio.sleep(wait)

        except APITimeoutError:
            if attempt == max_retries - 1:
                logger.error("LLM 调用超时，已重试 %d 次", max_retries)
                raise
            logger.warning(f"LLM 超时，重试中 (attempt {attempt+1})")
            await asyncio.sleep(1)

        except APIStatusError as e:
            if e.status_code >= 500:  # 服务端错误可重试
                wait = 2 ** attempt
                logger.warning(f"LLM 服务端错误 {e.status_code}，{wait}s 后重试")
                await asyncio.sleep(wait)
            else:
                logger.error(f"LLM 客户端错误 {e.status_code}: {e}")
                raise  # 400/401/403 等不重试

        except IndexError:
            logger.error("LLM 返回空 choices")
            raise ValueError("LLM 响应格式异常")

    raise Exception(f"LLM 调用失败，已重试 {max_retries} 次")


async def ask_llm_stream(messages: list, model: str = None) -> AsyncIterator[str]:
    """流式调用 LLM，yield 每个内容 chunk。"""
    client = get_client()
    model = model or config.LLM_MODEL

    try:
        stream = await client.chat.completions.create(
            model=model, messages=messages, stream=True
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content
    except (APITimeoutError, RateLimitError, APIStatusError) as e:
        logger.error(f"LLM 流式调用失败: {e}")
        yield f"\n\n[错误：LLM 调用失败，请稍后重试]"
```

**收益**:
- 限流自动等待，超时自动重试
- 30 秒超时而非 10 分钟
- 错误分类处理，用户看到友好提示
- 流式调用也有错误兜底

---

## 4. 事件总线：统一 SSE 输出

### DeepTutor 做法

```python
# core/stream_bus.py
class StreamBus:
    async def emit(self, event: StreamEvent): ...
    async def subscribe(self) -> AsyncIterator[StreamEvent]: ...
```

所有能力通过统一事件总线输出，前端/CLI/飞书都从同一个 bus 消费。

### AILearner 现状

SSE 事件生成器模式在 4 个文件中重复，每个都有细微差异：

| 文件 | try/except | save_state | 备注 |
|------|-----------|------------|------|
| `routes/chat.py:60-74` | ✅ | ✅ | 最完整 |
| `routes/evaluation.py:24-33` | ❌ | ✅ | 缺异常处理 |
| `routes/evaluation.py:43-56` | ✅ | ✅ | 有异常处理 |
| `agent/feishu.py:94-98` | ❌ | ❌（内联） | 重复 save 逻辑 |

### 改进方案

```python
# agent/stream_bus.py
"""轻量事件总线：统一 SSE 输出格式。"""

import asyncio
import json
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

    async def emit_tool_call(self, name: str, arguments: dict, call_id: str):
        """发送工具调用事件。"""
        await self.emit("tool_call", {
            "name": name,
            "arguments": arguments,
            "id": call_id,
        })

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


# routes/_common.py — 统一 SSE 生成器
import json
import logging
from typing import AsyncIterator, Callable, Awaitable

from fastapi.responses import StreamingResponse
from agent.stream_bus import StreamBus
from agent.schemas import SessionState
from db import save_state

logger = logging.getLogger(__name__)


async def sse_response(
    handler: Callable[[StreamBus], Awaitable[None]],
    state: SessionState,
    initial_msg_count: int,
) -> StreamingResponse:
    """统一的 SSE 响应包装器。

    Usage:
        async def my_handler(bus: StreamBus):
            await bus.emit_content("Hello")
            await bus.emit_done()

        return await sse_response(my_handler, state, len(state.messages))
    """
    bus = StreamBus()

    async def event_generator():
        try:
            # 启动 handler 任务
            task = asyncio.create_task(handler(bus))
            # 转发事件为 SSE 格式
            async for event in bus.events():
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            await task  # 确保 handler 完成
        except Exception as e:
            logger.exception("SSE handler error")
            yield f'data: {{"type":"error","text":"处理出错，请重试"}}\n\n'
        finally:
            # 持久化状态
            try:
                await save_state(state, initial_msg_count)
            except Exception:
                logger.exception("Failed to save state after SSE")

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# routes/chat.py — 使用示例
@router.post("/api/chat")
async def chat(request: ChatRequest):
    state = await get_or_create_session(request.session_id)
    initial_count = len(state.messages)
    state.messages.append(Message(role="user", content=request.message))

    async def handler(bus: StreamBus):
        async for event in handle_message(state, request.message, bus=bus):
            pass  # handle_message 内部通过 bus 发送事件

    return await sse_response(handler, state, initial_count)
```

**收益**:
- 4 处重复代码统一为 1 个 `sse_response`
- 异常处理、状态持久化只写一次
- handler 逻辑与 SSE 格式解耦
- 飞书等非 SSE 消费者也可使用同一个 bus

---

## 5. 会话管理：SessionStore 抽象

### DeepTutor 做法

- `SessionStore` 抽象接口
- SQLite / PocketBase 实现可切换
- 连接管理、WAL 模式、事务控制

### AILearner 现状

```python
# db.py
_conn: Optional[aiosqlite.Connection] = None  # 全局单连接

async def _get_conn() -> aiosqlite.Connection:
    global _conn
    if _conn is None:
        _conn = await aiosqlite.connect(config.DB_PATH)
        await _conn.execute("PRAGMA journal_mode=WAL")
    return _conn
```

问题：单连接并发瓶颈、无重试、无迁移、无过期清理。

### 改进方案

```python
# db.py — 改进版
"""会话持久化：SQLite 实现，支持并发和迁移。"""

import asyncio
import logging
from typing import Optional, List
import aiosqlite

import config
from agent.schemas import SessionState, Message

logger = logging.getLogger(__name__)

# 写锁：SQLite 只支持单写，用锁避免 "database is locked"
_write_lock = asyncio.Lock()
_conn: Optional[aiosqlite.Connection] = None

SCHEMA_VERSION = 1  # 递增触发迁移


async def _get_conn() -> aiosqlite.Connection:
    global _conn
    if _conn is None:
        _conn = await aiosqlite.connect(config.DB_PATH)
        await _conn.execute("PRAGMA journal_mode=WAL")
        await _conn.execute("PRAGMA foreign_keys=ON")
        await _conn.execute("PRAGMA busy_timeout=5000")  # 5s 等待锁
        await _init_db(_conn)
    return _conn


async def _init_db(conn: aiosqlite.Connection):
    """建表 + 迁移。"""
    await conn.executescript("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY
        );
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            evaluation_started INTEGER DEFAULT 0,
            evaluation_done INTEGER DEFAULT 0,
            evaluation_phase INTEGER DEFAULT 0,
            evaluation_path TEXT DEFAULT '',
            report TEXT DEFAULT '',
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        );
    """)
    # 检查版本，执行迁移
    cursor = await conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
    row = await cursor.fetchone()
    current = row[0] if row else 0
    if current < SCHEMA_VERSION:
        await _migrate(conn, current)
    await conn.commit()


async def _migrate(conn: aiosqlite.Connection, from_version: int):
    """数据库迁移钩子。"""
    if from_version < 1:
        # v1: 初始 schema，已在 _init_db 中创建
        pass
    # 未来迁移示例：
    # if from_version < 2:
    #     await conn.execute("ALTER TABLE sessions ADD COLUMN user_id TEXT DEFAULT ''")
    await conn.execute("DELETE FROM schema_version")
    await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))


async def get_or_create_session(session_id: str) -> SessionState:
    """获取或创建会话。"""
    conn = await _get_conn()
    cursor = await conn.execute(
        "SELECT evaluation_started, evaluation_done, evaluation_phase, evaluation_path, report "
        "FROM sessions WHERE session_id = ?", (session_id,)
    )
    row = await cursor.fetchone()
    if row:
        cursor = await conn.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id",
            (session_id,)
        )
        messages = [Message(role=r, content=c) for r, c in await cursor.fetchall()]
        return SessionState(
            session_id=session_id,
            messages=messages,
            evaluation_started=bool(row[0]),
            evaluation_done=bool(row[1]),
            evaluation_phase=row[2],
            evaluation_path=row[3] or "",
            report=row[4] or "",
        )
    # 新建
    async with _write_lock:
        await conn.execute(
            "INSERT OR IGNORE INTO sessions (session_id) VALUES (?)",
            (session_id,)
        )
        await conn.commit()
    return SessionState(session_id=session_id)


async def save_state(state: SessionState, initial_msg_count: int = 0):
    """保存状态，仅追加新消息。"""
    conn = await _get_conn()
    async with _write_lock:
        # 追加新消息
        for msg in state.messages[initial_msg_count:]:
            await conn.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                (state.session_id, msg.role, msg.content)
            )
        # 更新会话状态
        await conn.execute(
            "UPDATE sessions SET evaluation_started=?, evaluation_done=?, "
            "evaluation_phase=?, evaluation_path=?, report=?, updated_at=datetime('now') "
            "WHERE session_id=?",
            (
                int(state.evaluation_started),
                int(state.evaluation_done),
                state.evaluation_phase,
                state.evaluation_path,
                state.report,
                state.session_id,
            )
        )
        await conn.commit()


async def cleanup_expired_sessions(max_age_days: int = 30):
    """清理过期会话（定期调用）。"""
    conn = await _get_conn()
    async with _write_lock:
        await conn.execute(
            "DELETE FROM messages WHERE session_id IN "
            "(SELECT session_id FROM sessions WHERE updated_at < datetime('now', ?))",
            (f"-{max_age_days} days",)
        )
        await conn.execute(
            "DELETE FROM sessions WHERE updated_at < datetime('now', ?)",
            (f"-{max_age_days} days",)
        )
        await conn.commit()


async def close_db():
    """关闭数据库连接。"""
    global _conn
    if _conn:
        await _conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        await _conn.close()
        _conn = None
```

**收益**:
- 写锁避免 "database is locked"
- `busy_timeout=5000` 让读操作等待写锁释放
- 迁移框架：改 schema 不会丢数据
- 过期清理：sessions 表不会无限增长
- 外键约束真正生效

---

## 6. 认证中间件：轻量可开关

### DeepTutor 做法

- 可配置开关 `AUTH_ENABLED`
- JWT + Cookie 双模式
- 角色权限 (`admin` / `user`)
- 中间件统一拦截

### AILearner 现状

零认证，所有端点裸奔。

### 改进方案

```python
# auth.py
"""轻量认证：API Key 模式，可通过环境变量开关。"""

import os
from fastapi import Depends, HTTPException, Header, Request
from typing import Optional

API_KEY = os.getenv("API_KEY", "")  # 空 = 不启用（开发模式）


async def verify_auth(request: Request):
    """认证依赖项。

    - 未设置 API_KEY 时跳过认证（开发模式）
    - 支持 Header: Authorization: Bearer <key>
    - 支持 Query: ?api_key=<key>（用于 SSE 等不方便设 Header 的场景）
    """
    if not API_KEY:
        return  # 开发模式，跳过认证

    # 从 Header 获取
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer ") and auth[7:] == API_KEY:
        return

    # 从 Query 获取（SSE fallback）
    key = request.query_params.get("api_key")
    if key == API_KEY:
        return

    raise HTTPException(status_code=401, detail="Unauthorized")


# main.py — 注册为全局依赖
from auth import verify_auth

app = FastAPI(..., dependencies=[Depends(verify_auth)])

# 或者只保护特定路由：
# @router.post("/api/chat", dependencies=[Depends(verify_auth)])
```

```env
# .env
API_KEY=your-secret-key-here  # 留空则不启用认证
```

**收益**:
- 一行环境变量控制开关
- 支持 Header 和 Query 两种方式（SSE 需要 Query）
- 开发时留空即可，零摩擦
- 不引入 JWT 等复杂度

---

## 7. 配置管理：分离关注点

### DeepTutor 做法

基础设施配置和业务数据分离到不同服务（虽然 RuntimeSettingsService 本身过大）。

### AILearner 现状

`config.py` 256 行，82% 是业务数据（评估问题、场景模板），与 API Key、端口混在一起。

### 改进方案

```
config/
  __init__.py          # 统一导出
  settings.py          # 基础设施配置（API Key、端口、模型名）
  evaluation.py        # 评估问题定义
  scenarios.py         # AI 使用场景模板
```

```python
# config/settings.py
"""基础设施配置：从环境变量读取。"""
import os
from dotenv import load_dotenv

load_dotenv()

# LLM
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "siliconflow")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-V4-Flash")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.siliconflow.cn/v1")

# API Keys
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

# Server
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))

# Database
DB_PATH = os.getenv("DB_PATH", "ailearner.db")

# Feishu
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
FEISHU_ENCRYPT_KEY = os.getenv("FEISHU_ENCRYPT_KEY", "")  # 新增：签名验证用


def get_api_key() -> str:
    """获取当前 provider 的 API key。"""
    if LLM_PROVIDER == "deepseek":
        return DEEPSEEK_API_KEY or SILICONFLOW_API_KEY
    return SILICONFLOW_API_KEY or DEEPSEEK_API_KEY


# config/evaluation.py
"""评估问题定义：修改问题只需改这个文件。"""

EVALUATION_QUESTIONS = [
    {
        "id": "q1_background",
        "question": "你目前的职业或身份是？",
        "options": ["上班族/白领", "学生", "自由职业/个体", "其他"],
    },
    # ... 其余问题 ...
]

LEARN_AI_QUESTIONS = [
    {
        "id": "lq1_direction",
        "question": "你最想学哪个方向？",
        "options": ["AI 绘画", "AI 写作", "AI 编程", "AI 办公", "还没想好"],
    },
    # ... 其余问题 ...
]
```

```python
# config/__init__.py — 统一导出，保持向后兼容
from config.settings import *
from config.evaluation import *
from config.scenarios import *
```

**收益**:
- 改评估问题只需编辑 `evaluation.py`，不碰基础设施代码
- 配置文件可独立审查
- 未来可进一步外部化为 YAML/JSON

---

## 8. 消息截断：上下文窗口控制

### DeepTutor 做法

三层记忆系统 (L1/L2/L3)，自动管理上下文窗口，支持摘要压缩。

### AILearner 现状

```python
# agent/core.py:119-125
for m in state.messages[:-1]:
    msgs.append({"role": m.role, "content": m.content})
```

全量历史回传，100 轮对话 = 100+ 条消息全部发给 LLM。

### 改进方案

```python
# agent/llm_client.py — 新增函数

# 配置
MAX_CONTEXT_MESSAGES = 20     # 最近 20 条消息
MAX_CONTEXT_CHARS = 6000      # 粗估 ~4000 tokens（中文 ~1.5 token/字）
CHARS_PER_TOKEN = 1.5         # 中文平均 token/字比率


def build_messages(
    state_messages: list,
    system_prompt: str,
    max_messages: int = MAX_CONTEXT_MESSAGES,
    max_chars: int = MAX_CONTEXT_CHARS,
) -> list:
    """构建 LLM 消息列表，自动截断历史。

    策略：
    1. 始终包含 system prompt
    2. 取最近 max_messages 条消息
    3. 在消息数量限制内，进一步按总字符数截断
    4. 如果截断了，在开头插入一条摘要提示
    """
    msgs = [{"role": "system", "content": system_prompt}]

    if not state_messages:
        return msgs

    # 取最近 N 条
    recent = state_messages[-max_messages:]

    # 按字符数截断（从最新的往回数）
    total_chars = 0
    included = []
    for m in reversed(recent):
        chars = len(m.content or "")
        if total_chars + chars > max_chars and included:
            break
        included.append(m)
        total_chars += chars

    included.reverse()  # 恢复时间顺序

    # 如果截断了，添加上下文提示
    truncated_count = len(state_messages) - len(included)
    if truncated_count > 0:
        msgs.append({
            "role": "system",
            "content": f"（以下是最近的对话，之前还有 {truncated_count} 条历史已省略）"
        })

    for m in included:
        msgs.append({"role": m.role, "content": m.content})

    return msgs


# agent/core.py — normal_chat() 改用 build_messages
async def normal_chat(state: SessionState, user_text: str, bus: StreamBus = None):
    msgs = build_messages(state.messages, config.SYSTEM_PROMPT)
    msgs.append({"role": "user", "content": user_text})

    response = await ask_llm(msgs)
    # ... 后续逻辑 ...
```

**收益**:
- 长对话不会溢出上下文窗口
- 控制 API 成本（每次调用的 token 数可控）
- 截断时有提示，LLM 知道有历史省略
- 可通过 `MAX_CONTEXT_MESSAGES` 和 `MAX_CONTEXT_CHARS` 灵活调节

---

## 9. 测试体系：从 0 到基础覆盖

### DeepTutor 做法

304 个测试文件，0.5:1 测试比。conftest 提供可复用 fixtures（mock LLM、test DB、fake context）。

### AILearner 现状

仅 `test_personas.py` 一个端到端集成测试，无单元测试。

### 改进方案

```
tests/
  __init__.py
  conftest.py               # 共享 fixtures
  test_state_machine.py     # 评估状态机单元测试
  test_tools.py             # 工具执行测试
  test_retriever.py         # 知识检索测试
  test_llm_client.py        # LLM 客户端测试（mock）
  test_chat_api.py          # API 集成测试
  test_db.py                # 数据库操作测试
```

```python
# tests/conftest.py
"""共享 fixtures：mock LLM、内存数据库、测试用 SessionState。"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from agent.schemas import SessionState, Message


@pytest.fixture
def mock_llm(monkeypatch):
    """Mock LLM 调用，返回预设响应。"""
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="测试回复"))]
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    import agent.core
    monkeypatch.setattr(agent.core, "get_client", lambda: mock_client)
    return mock_client


@pytest.fixture
def fresh_state():
    """全新的会话状态。"""
    return SessionState(session_id="test-session-001")


@pytest.fixture
def eval_in_progress():
    """评估进行中的会话状态。"""
    return SessionState(
        session_id="test-eval-001",
        messages=[Message(role="user", content="开始评估")],
        evaluation_started=True,
        evaluation_phase=1,
        evaluation_path="use",
    )


@pytest.fixture
def tmp_db(tmp_path):
    """临时数据库，测试后自动清理。"""
    import config
    old_path = config.DB_PATH
    config.DB_PATH = str(tmp_path / "test.db")
    yield config.DB_PATH
    config.DB_PATH = old_path


# tests/test_state_machine.py
"""评估状态机测试：覆盖所有路径。"""

import pytest
from agent.evaluation.state_machine import (
    should_start_evaluation,
    is_evaluation_in_progress,
    continue_evaluation,
    _resolve_answer,
)


class TestShouldStartEvaluation:
    def test_keyword_trigger(self):
        assert should_start_evaluation("我想评估一下") is True

    def test_normal_message(self):
        assert should_start_evaluation("你好") is False


class TestResolveAnswer:
    def test_numeric_option(self):
        q = {"options": ["A", "B", "C"]}
        assert _resolve_answer("2", q) == "B"

    def test_text_match(self):
        q = {"options": ["上班族", "学生", "自由职业"]}
        assert _resolve_answer("我是学生", q) == "学生"

    def test_no_match(self):
        q = {"options": ["A", "B"]}
        assert _resolve_answer("完全无关", q) is None


class TestContinueEvaluation:
    @pytest.mark.asyncio
    async def test_phase0_background(self, fresh_state):
        fresh_state.evaluation_started = True
        fresh_state.evaluation_phase = 0
        events = []
        async for event in continue_evaluation(fresh_state, "1"):
            events.append(event)
        assert any(e.get("type") == "content" for e in events)
        assert fresh_state.evaluation_phase == 1

    @pytest.mark.asyncio
    async def test_invalid_input_reprompts(self, fresh_state):
        fresh_state.evaluation_started = True
        fresh_state.evaluation_phase = 0
        events = []
        async for event in continue_evaluation(fresh_state, "xyz"):
            events.append(event)
        assert any("没听清" in e.get("text", "") for e in events)
```

**收益**:
- 状态机是最高风险模块，单元测试覆盖所有路径
- Mock LLM 让测试快速且不依赖网络
- 临时数据库避免测试污染
- `conftest` fixtures 可复用

---

## 10. Docker 改进

### DeepTutor 做法

- 多阶段构建（前端/后端分离）
- 健康检查验证服务可用性
- 沙箱 runner 独立容器

### AILearner 现状

```dockerfile
# Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .                    # 包含 .env、.git、__pycache__
RUN pip install ...
CMD ["uvicorn", "main:app", ...]
```

### 改进方案

```dockerfile
# Dockerfile
FROM python:3.11-slim AS base

WORKDIR /app

# 依赖层（缓存友好）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码
COPY main.py config.py db.py ./
COPY agent/ agent/
COPY routes/ routes/
COPY knowledge/ knowledge/
COPY web/ web/

# 不 COPY: .env, .git, __pycache__, *.db, test_personas.py, tuifei_tool/

RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import httpx; r=httpx.get('http://localhost:8000/'); assert r.status_code==200"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```yaml
# docker-compose.yml
services:
  app:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./ailearner.db:/app/ailearner.db       # 数据库持久化
      - ./knowledge/data:/app/knowledge/data    # 知识库可热更新
    env_file:
      - .env
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c",
             "import httpx; r=httpx.get('http://localhost:8000/'); assert r.status_code==200"]
      interval: 30s
      timeout: 5s
      retries: 3
```

```gitignore
# .dockerignore
.env
.git
__pycache__
*.db
*.db-wal
*.db-shm
test_*.py
tuifei_tool/
.cc-connect/
*.docx
*.xlsx
```

**收益**:
- `.env` 不会 bake 进镜像
- 知识库外部挂载，更新文章无需重建镜像
- 健康检查验证应用可用性，而非只检查端口
- 依赖层缓存，构建更快

---

## 11. 实施路线图

### Phase 1：稳定性（1-2 天）

| 任务 | 文件 | 预估 |
|------|------|------|
| LLM 重试 + 超时 | `agent/llm_client.py` 新建 | 2h |
| 消息截断 | `agent/llm_client.py` 新增 `build_messages()` | 1h |
| Session 写锁 | `db.py` 改进 | 1h |
| 评估状态机边界检查 | `agent/core.py` 修改 | 1h |

### Phase 2：安全性（1 天）

| 任务 | 文件 | 预估 |
|------|------|------|
| API Key 认证中间件 | `auth.py` 新建 | 1h |
| 服务端 Session ID | `routes/chat.py` 修改 | 0.5h |
| 飞书签名验证 | `agent/feishu.py` 修改 | 1h |
| 错误消息脱敏 | `routes/chat.py`, `evaluation.py` | 0.5h |

### Phase 3：可维护性（2-3 天）

| 任务 | 文件 | 预估 |
|------|------|------|
| 拆分 core.py | `agent/orchestrator.py`, `evaluation/` 新建 | 3h |
| StreamBus | `agent/stream_bus.py` 新建 | 1h |
| 统一 SSE 生成器 | `routes/_common.py` 改进 | 1h |
| 工具协议 ABC | `agent/tools/base.py`, `registry.py` 新建 | 2h |
| 配置分离 | `config/settings.py`, `evaluation.py` 新建 | 1h |

### Phase 4：质量保障（1-2 天）

| 任务 | 文件 | 预估 |
|------|------|------|
| 测试 conftest | `tests/conftest.py` 新建 | 1h |
| 状态机测试 | `tests/test_state_machine.py` 新建 | 2h |
| LLM 客户端测试 | `tests/test_llm_client.py` 新建 | 1h |
| DB 迁移框架 | `db.py` 改进 | 1h |
| Docker 改进 | `Dockerfile`, `docker-compose.yml` | 1h |

### 总预估：6-9 天

---

## 附录：改造前后对比

| 维度 | 改造前 | 改造后 |
|------|--------|--------|
| core.py | 588 行，7 职责 | 拆为 4 文件，各 < 200 行 |
| LLM 调用 | 裸调用，零容错 | 重试 3 次，30s 超时，错误分类 |
| 消息历史 | 全量回传 | 最近 20 条 + 6000 字截断 |
| SSE 输出 | 4 处重复代码 | 1 个 `sse_response` 统一处理 |
| 工具新增 | 改 2 处 if/elif | 实现 ABC + register() |
| 认证 | 无 | API Key 可开关 |
| 并发安全 | 无锁，可能 "database is locked" | 写锁 + busy_timeout |
| 测试 | 1 个集成测试 | 6+ 个单元测试文件 |
| 配置 | 256 行混合文件 | 3 个职责清晰的文件 |
| Docker | .env 可能泄露 | .dockerignore + 外部挂载 |
