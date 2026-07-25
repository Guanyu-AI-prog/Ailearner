"""LLM 客户端：封装调用、重试、超时、错误处理、消息截断。"""

import asyncio
import logging
from typing import AsyncIterator, Dict, List, Optional

from openai import AsyncOpenAI, APITimeoutError, RateLimitError, APIStatusError

from config import config

logger = logging.getLogger(__name__)

_client: Optional[AsyncOpenAI] = None

# 消息截断配置
MAX_CONTEXT_MESSAGES = 20
MAX_CONTEXT_CHARS = 6000


def get_client() -> AsyncOpenAI:
    """获取 AsyncOpenAI 单例，带 30s 超时。"""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL,
            timeout=30.0,
        )
    return _client


async def ask_llm(
    messages: List[Dict],
    tools: Optional[List] = None,
    model: Optional[str] = None,
    max_retries: int = 3,
) -> str:
    """调用 LLM，自动重试瞬态错误，返回文本内容。"""
    client = get_client()
    model_name = model or config.LLM_MODEL

    kwargs = {
        "model": model_name,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    for attempt in range(max_retries):
        try:
            response = await client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content
            if not content:
                raise ValueError("LLM 返回空内容")
            return content

        except RateLimitError:
            wait = 2 ** attempt
            logger.warning(f"LLM 限流，{wait}s 后重试 (attempt {attempt + 1}/{max_retries})")
            await asyncio.sleep(wait)

        except APITimeoutError:
            if attempt == max_retries - 1:
                logger.error("LLM 调用超时，已重试 %d 次", max_retries)
                raise
            logger.warning(f"LLM 超时，重试中 (attempt {attempt + 1}/{max_retries})")
            await asyncio.sleep(1)

        except APIStatusError as e:
            if e.status_code >= 500:
                wait = 2 ** attempt
                logger.warning(f"LLM 服务端错误 {e.status_code}，{wait}s 后重试")
                await asyncio.sleep(wait)
            else:
                logger.error(f"LLM 客户端错误 {e.status_code}: {e}")
                raise

        except IndexError:
            logger.error("LLM 返回空 choices")
            raise ValueError("LLM 响应格式异常")

    raise Exception(f"LLM 调用失败，已重试 {max_retries} 次")


async def ask_llm_stream(
    messages: List[Dict],
    tools: Optional[List] = None,
    model: Optional[str] = None,
):
    """流式调用 LLM，返回原始 response 对象（async iterable）。

    调用方负责迭代 chunk。出错时返回 None，调用方应跳过。
    """
    client = get_client()
    model_name = model or config.LLM_MODEL

    kwargs = {
        "model": model_name,
        "messages": messages,
        "stream": True,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    try:
        return await client.chat.completions.create(**kwargs)
    except (APITimeoutError, RateLimitError, APIStatusError) as e:
        logger.error(f"LLM 流式调用失败: {e}")
        return None


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
    4. 如果截断了，在开头插入一条上下文提示
    """
    msgs = [{"role": "system", "content": system_prompt}]

    if not state_messages:
        return msgs

    recent = state_messages[-max_messages:]

    total_chars = 0
    included = []
    for m in reversed(recent):
        chars = len(m.content or "")
        if total_chars + chars > max_chars and included:
            break
        included.append(m)
        total_chars += chars

    included.reverse()

    truncated_count = len(state_messages) - len(included)
    if truncated_count > 0:
        msgs.append({
            "role": "system",
            "content": f"（以下是最近的对话，之前还有 {truncated_count} 条历史已省略）",
        })

    for m in included:
        msgs.append({"role": m.role, "content": m.content})

    return msgs
