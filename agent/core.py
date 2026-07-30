"""消息处理：流式响应 + 普通对话 + 工具调用。"""

from typing import Dict, List, Optional

from config import config
from agent.schemas import Message, SessionState
from agent.prompts import SYSTEM_PROMPT
from agent.tools import get_definitions, execute as execute_tool
from agent.llm_client import ask_llm_stream, build_messages
from knowledge.retriever import retrieve_knowledge


async def generate_stream(messages: List[Dict], tools: Optional[List] = None):
    """流式调用 LLM，yield 内容和工具调用事件。"""
    response = await ask_llm_stream(messages, tools=tools)
    if response is None:
        yield {"type": "content", "text": "\n\n[错误：LLM 调用失败，请稍后重试]"}
        return
    tool_calls_buffer = {}
    async for chunk in response:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta is None:
            continue
        if delta.content:
            yield {"type": "content", "text": delta.content}
        if delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index
                if idx not in tool_calls_buffer:
                    tool_calls_buffer[idx] = {"id": "", "name": "", "arguments": ""}
                if tc.id:
                    tool_calls_buffer[idx]["id"] = tc.id
                if tc.function.name:
                    tool_calls_buffer[idx]["name"] += tc.function.name
                if tc.function.arguments:
                    tool_calls_buffer[idx]["arguments"] += tc.function.arguments
    if tool_calls_buffer:
        for tc_data in tool_calls_buffer.values():
            yield {"type": "tool_call", "name": tc_data["name"], "arguments": tc_data["arguments"], "id": tc_data["id"]}


async def build_context(state: SessionState, user_message: str) -> str:
    """从知识库检索相关上下文。"""
    relevant = retrieve_knowledge(user_message, n_results=3)
    if not relevant:
        return ""
    context = "以下是从知识库中找到的相关信息：\n\n"
    for doc, metadata in relevant:
        tags = ", ".join(metadata.get("tags", []))
        context += f"---\n来源：{metadata.get('title', '未知')}\n"
        if tags:
            context += f"标签：{tags}\n"
        context += f"{doc}\n\n"
    context += "请基于以上信息回答用户问题。如果信息不够，可以告诉用户你需要搜索。"
    return context


async def normal_chat(state: SessionState, message: str, stream: bool = True):
    """普通对话：构建上下文、调用 LLM、处理工具调用。"""
    context = await build_context(state, message)
    msgs = build_messages(state.messages[:-1], SYSTEM_PROMPT)
    user_content = message
    if context:
        user_content = f"{message}\n\n{context}"
    msgs.append({"role": "user", "content": user_content})

    if stream:
        full_content = ""
        tool_calls_buffer = []
        async for chunk in generate_stream(msgs, tools=get_definitions()):
            if chunk["type"] == "content":
                full_content += chunk["text"]
                yield {"type": "content", "text": chunk["text"]}
            elif chunk["type"] == "tool_call":
                tool_calls_buffer.append(chunk)

        if tool_calls_buffer:
            assistant_tool_calls = []
            tool_results = []
            for tc in tool_calls_buffer:
                tc_id = tc.get("id", "") or f"call_{tc['name']}"
                assistant_tool_calls.append({
                    "id": tc_id, "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]}
                })
                yield {"type": "status", "text": f"\n\n> 正在调用工具：{tc['name']}..."}
                result = await execute_tool(tc["name"], tc["arguments"])
                tool_results.append({"tool_call_id": tc_id, "content": result})
                yield {"type": "status", "text": f"> 工具 {tc['name']} 执行完成\n\n"}

            msgs.append({"role": "assistant", "content": None, "tool_calls": assistant_tool_calls})
            for tr in tool_results:
                msgs.append({"role": "tool", **tr})

            yield {"type": "status", "text": "> 正在生成回复...\n\n"}
            async for chunk2 in generate_stream(msgs):
                if chunk2["type"] == "content":
                    full_content += chunk2["text"]
                    yield chunk2

        state.messages.append(Message(role="assistant", content=full_content))
    else:
        # 非流式：复用 generate_stream，收集全部内容
        full_content = ""
        tool_calls_buffer = []
        async for chunk in generate_stream(msgs, tools=get_definitions()):
            if chunk["type"] == "content":
                full_content += chunk["text"]
            elif chunk["type"] == "tool_call":
                tool_calls_buffer.append(chunk)

        if tool_calls_buffer:
            assistant_tool_calls = []
            tool_results = []
            for tc in tool_calls_buffer:
                tc_id = tc.get("id", "") or f"call_{tc['name']}"
                assistant_tool_calls.append({
                    "id": tc_id, "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]}
                })
                result = await execute_tool(tc["name"], tc["arguments"])
                tool_results.append({"tool_call_id": tc_id, "content": result})

            msgs.append({"role": "assistant", "content": None, "tool_calls": assistant_tool_calls})
            for tr in tool_results:
                msgs.append({"role": "tool", **tr})

            async for chunk2 in generate_stream(msgs):
                if chunk2["type"] == "content":
                    full_content += chunk2["text"]

        state.messages.append(Message(role="assistant", content=full_content))
        yield {"type": "content", "text": full_content}
