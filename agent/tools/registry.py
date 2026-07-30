"""工具注册表：自动发现、定义导出、按名称执行。"""

import json
import logging
from typing import Dict, List

from agent.tools.base import BaseTool

logger = logging.getLogger(__name__)

_registry: Dict[str, BaseTool] = {}


def register(tool: BaseTool):
    """注册工具到全局注册表。"""
    name = tool.get_definition()["function"]["name"]
    _registry[name] = tool


def get_definitions() -> List[dict]:
    """返回所有工具的 JSON Schema 定义，用于 LLM 调用。"""
    return [t.get_definition() for t in _registry.values()]


async def execute(name: str, arguments) -> str:
    """按名称执行工具。"""
    tool = _registry.get(name)
    if not tool:
        return f"未知工具：{name}"
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
        return await tool.execute(**args)
    except json.JSONDecodeError as e:
        return f"工具参数解析失败：{str(e)}"
    except Exception as e:
        logger.error(f"工具 {name} 执行出错：{e}", exc_info=True)
        return f"工具执行出错：{str(e)}"
