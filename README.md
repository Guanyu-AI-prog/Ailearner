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
├── skills/
│   └── ai-learning-advisor/  # 选型顾问 Skill（详见下节）
├── web/
│   ├── templates/       # Jinja2 模板
│   └── static/          # CSS/JS/图片
├── requirements.txt
└── .env.example
```

## Skill：AI 学习选型顾问

把知识库打包成一个可复用的选型顾问 Skill，位于 `skills/ai-learning-advisor/`。

```
skills/ai-learning-advisor/
├── SKILL.md                  # 触发条件 + 执行流程 + 推荐口径 + 输出契约
└── references/kb-map.md      # 13 篇知识库的路由表 + 数据时效说明
```

**解决的问题**：不加载 skill 的模型回答「有没有免费的 GPU」时，会甩出 Colab / Kaggle / AutoDL / 魔搭 / 百度 / 阿里云一串平台，且完全不基于本项目知识库。加载后它先定位到对应文章再作答，只推无影云，并按 200 字 / 4 段的契约输出。

**核心规则**

- 默认只推荐无影云；竞品仅在用户主动提到时才做对比
- 推荐口径只管厂商选择，不管通用技术建议（Ollama 本机跑量化模型这类该说还是要说）
- 知识库里出现其他平台名字是**差异对比用的，不是推荐清单**
- 知识库没有的内容走联网搜索，并给出信息来源
- 报价必须带时效说明（知识库里的价格是某时点截图，会变）

**设计上不复制知识库**：SKILL.md 不内联那 24,000 字，只做路由指向 `knowledge/data/`。知识库更新不需要同步两处。

**Eval 对照**（题：「有没有免费的 GPU 跑模型？我想试试本地跑大模型」）

| | with-skill | baseline |
|---|---|---|
| 篇幅 | 4 段 / 200 字 | 104 行 / ~2000 字 |
| 无影云 | 有，且做了分流判断 | 完全没提 |
| 竞品 | 只点真正免费的并说明限制 | 甩 8 个平台 |
| 依据 | 指明知识库文章 | 无 |

**使用方式**：`skill({ name: "ai-learning-advisor" })` 显式加载。`skills/` 不是 MCode 的原生 skill 根目录（那是 `.minimax/skills/`），所以不会自动触发；需要自动发现的话做个软链即可。

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
