# AI 学习引路人（AILearnerAgent）

判断该不该学 AI、学什么方向、怎么零成本入门的智能 Agent。

## 快速开始

```bash
cd ailearner
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env，填入硅基流动 API Key
python main.py
```

打开 http://localhost:8000

## 配置说明

本项目使用**硅基流动**的 OpenAI 兼容 API。在 `.env` 中配置：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LLM_API_KEY` | 硅基流动 API Key | - |
| `LLM_BASE_URL` | API 地址 | `https://api.siliconflow.cn/v1` |
| `LLM_MODEL` | 模型名称 | `deepseek-ai/DeepSeek-V2.5` |

也兼容任何 OpenAI 格式的 API（填对应 `base_url` 和 `key` 即可）。

## 核心功能

- **入门评估**：7 个问题判断是否适合学 AI、学什么方向、学到什么水平
- **RAG 知识库**：基于 numpy 的轻量语义搜索
- **工具调用**：Web 搜索、云电脑推荐、学习路径生成
- **零成本方案**：优先推荐免费资源和路径

## 项目结构

```
ailearner/
├── main.py              # FastAPI 入口
├── config.py            # 配置管理
├── agent/
│   ├── core.py          # 对话和评估编排
│   ├── tools.py         # 工具定义
│   ├── prompts.py       # 系统提示词
│   └── schemas.py       # 数据模型
├── knowledge/
│   ├── loader.py        # 知识库解析
│   ├── retriever.py     # 语义检索
│   └── data/resources.md  # 学习资源
├── web/
│   ├── templates/       # HTML 模板
│   └── static/          # CSS/JS
├── requirements.txt
└── .env.example
```

## 技术栈

FastAPI + OpenAI SDK + SiliconFlow API
