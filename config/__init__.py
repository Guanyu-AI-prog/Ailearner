"""配置模块：统一导出，保持向后兼容。"""

from config.settings import Settings, settings
from config.evaluation import *

# 向后兼容：代码中 `from config import config` 仍然可用
# config 对象包含所有配置项
class Config(Settings):
    """合并基础设施配置和业务数据的兼容类。"""
    pass

# 将 evaluation 模块的常量挂到 Config 类上
import config.evaluation as _eval
for _name in dir(_eval):
    if not _name.startswith('_'):
        setattr(Config, _name, getattr(_eval, _name))

config = Config()

__all__ = ["config", "Config", "Settings", "settings"]
