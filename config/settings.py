"""基础设施配置：从环境变量读取。"""

import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env", override=True)


class Settings:
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "siliconflow").lower()

    SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-reasoner")

    # 最终生效的 LLM 配置（优先级：手动指定 > 当前 provider 配置）
    _manual_key = os.getenv("LLM_API_KEY", "")
    _manual_url = os.getenv("LLM_BASE_URL", "")
    _manual_model = os.getenv("LLM_MODEL", "")

    if LLM_PROVIDER == "deepseek":
        LLM_API_KEY = _manual_key or DEEPSEEK_API_KEY
        LLM_BASE_URL = _manual_url or DEEPSEEK_BASE_URL
        LLM_MODEL = _manual_model or DEEPSEEK_MODEL
    else:
        LLM_API_KEY = _manual_key or SILICONFLOW_API_KEY
        LLM_BASE_URL = _manual_url or "https://api.siliconflow.cn/v1"
        LLM_MODEL = _manual_model or "deepseek-ai/DeepSeek-V4-Flash"

    FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
    FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")

    KNOWLEDGE_DIR = ROOT_DIR / os.getenv("KNOWLEDGE_DIR", "knowledge/data")

    APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT = int(os.getenv("APP_PORT", "8000"))


settings = Settings()
