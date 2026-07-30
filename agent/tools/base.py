"""工具基类：实现 get_definition() 和 execute() 即可注册。"""

from abc import ABC, abstractmethod


class BaseTool(ABC):
    """工具基类。"""

    @abstractmethod
    def get_definition(self) -> dict:
        """返回 OpenAI function calling 格式的工具定义。"""
        ...

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """执行工具，返回字符串结果。"""
        ...
