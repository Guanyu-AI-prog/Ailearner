# AI 学习引路人（AILearnerAgent）

一个帮助普通人判断"该不该学 AI、学什么方向、怎么零成本入门"的智能 Agent。

## 功能

- **智能评估**：7 个问题判断用户是否适合学 AI、学到什么程度、推荐什么方向
- **知识库检索**：基于标签路由匹配学习资源文章，零外部依赖
- **工具调用**：网络搜索、云电脑推荐、学习路径生成
- **流式对话**：SSE 实时输出，体验流畅
- **会话持久化**：SQLite 存储，重启不丢对话

## 技术栈

| 组件 | 技术选型 | 选型理由 |
|------|----------|----------|
| 后端框架 | FastAPI | 异步支持好，自带 OpenAPI 文档 |
| LLM 对接 | OpenAI SDK（兼容 API） | 硅基流动 / DeepSeek 等都兼容 |
| 知识检索 | 标签路由（tags.json） | 零依赖，无需向量数据库 |
| 会话存储 | SQLite | 单文件数据库，零运维 |
| 前端 | Jinja2 + 原生 JS | 无框架依赖，部署简单 |

## 架构

```
用户 → 浏览器(FastAPI渲染) → main.py(FastAPI)
                                  ↓
                          agent/core.py (核心路由)
                          ↓              ↓
                    knowledge/        agent/tools.py
                    retriever.py      (搜索/推荐/路径)
                    (标签路由)
                          ↓
                    config.py → LLM API (硅基流动)
```

## 快速开始

### 本地运行

```bash
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env，填入 API Key
python main.py
```

打开 http://localhost:8000/chat

### Docker 部署

```bash
cp .env.example .env
# 编辑 .env，填入 API Key
docker-compose up -d
```

打开 http://localhost:8000/chat

## 项目结构

```
ailearner/
├── main.py              # FastAPI 入口，路由
├── config.py            # 配置管理（LLM、评估问卷、场景模板）
├── db.py                # SQLite 会话持久化
├── agent/
│   ├── core.py          # 核心对话逻辑（评估/正常对话/报告生成）
│   ├── schemas.py       # 数据模型
│   ├── prompts.py       # 系统提示词
│   └── tools.py         # 工具定义和执行
├── knowledge/
│   ├── loader.py        # Markdown 解析
│   ├── retriever.py     # 标签路由检索
│   ├── tags.json        # 文章标签映射
│   └── data/            # 知识库 Markdown 文件
├── web/
│   ├── templates/       # Jinja2 模板
│   └── static/          # CSS/JS/图片
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## 评估流程

```
用户说"帮我评估"
  → 触发关键词匹配
    → 逐个提问（7 题：目标/背景/时间/数学/编程/预算/方向）
      → 收集回答存入 SQLite
        → 生成评估报告（规则引擎）
          → 输出建议（学/不学 + 水平 + 方向 + 路径）
```

## 配置说明

在 `.env` 中配置：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LLM_API_KEY` | LLM API Key | - |
| `LLM_BASE_URL` | API 地址 | `https://api.siliconflow.cn/v1` |
| `LLM_MODEL` | 模型名称 | `deepseek-ai/DeepSeek-V4-Flash` |

兼容任何 OpenAI 格式的 API（填对应 `base_url` 和 `key` 即可）。
