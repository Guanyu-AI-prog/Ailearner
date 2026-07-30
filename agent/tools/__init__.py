"""工具模块：启动时注册所有工具。"""

from agent.tools.registry import register, get_definitions, execute
from agent.tools.web_search import WebSearchTool
from agent.tools.cloud_computer import CloudComputerTool
from agent.tools.learning_path import LearningPathTool

register(WebSearchTool())
register(CloudComputerTool())
register(LearningPathTool())

__all__ = ["get_definitions", "execute"]
