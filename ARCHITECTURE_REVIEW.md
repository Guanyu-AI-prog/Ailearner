# ailearner 项目架构审查报告

> 审查时间：2026-07-13
> 项目版本：修复后的当前版本
> 总有效代码量：约 1,500 行

---

## 一、项目结构总览

```
ailearner/
├── main.py              (158行) FastAPI 路由 + SSE 流式
├── config.py            (240行) 环境配置 + 全部业务数据
├── db.py                (110行) 异步 SQLite 数据层
├── agent/
│   ├── core.py          (588行) LLM调用 + 评估状态机 + 报告生成
│   ├── tools.py         (252行) 工具定义 + 实现 + 注册
│   ├── prompts.py       (65行)  System Prompt
│   ├── schemas.py       (24行)  Pydantic 模型
│   └── feishu.py        (118行) 飞书机器人
├── knowledge/
│   └── retriever.py     (104行) 关键词检索
├── web/
│   ├── templates/       Jinja2 模板
│   └── static/          CSS + JS
└── requirements.txt
```

---

## 二、架构评价

### ✅ 做得好的部分

| 方面 | 评价 |
|------|------|
| **分层清晰** | 路由层 (main.py) → 业务层 (agent/) → 数据层 (db.py) → 知识层 (knowledge/) 职责划分明确 |
| **async-first** | FastAPI + aiosqlite + AsyncOpenAI，全链路异步，不会阻塞事件循环 |
| **SSE 流式输出** | 用户体验好，实时看到回复 |
| **Schema 隔离** | Pydantic 模型独立文件，请求/响应类型安全 |
| **Docker 化** | Dockerfile + docker-compose 齐全，可一键部署 |
| **配置外部化** | 环境变量 + .env，不硬编码密钥 |

### 🟡 架构层面的隐患

#### 1. `core.py` 是个 588 行的"上帝文件"

它同时承担了 5 个职责：

- LLM 客户端管理 (`get_client`, `ask_llm`)
- 流式响应生成 (`generate_stream`)
- 评估状态机 (`start_evaluation`, `continue_evaluation`)
- 报告生成 (`generate_report`, `_render_use_ai_report`)
- 知识检索编排 (`build_context`)

这是**屎山化最明显的信号**。当需求增长时（比如加新的评估路径、新的报告格式、新的对话模式），这个文件会变成没人敢碰的 2000 行怪物。

#### 2. `config.py` 混合了两类完全不同的东西

```python
class Config:
    LLM_API_KEY = ...           # ← 基础设施配置
    EVALUATION_FIRST_QUESTION   # ← 业务内容数据
    USE_AI_SCENARIOS            # ← 业务内容数据（210行 prompt 模板）
```

环境配置和业务数据耦合在一个类里。每次加一个评估问题或 prompt 模板，都要改 config.py。内容运营和技术配置混在一起。

#### 3. 评估状态机是隐式的

```python
# 状态由 整数 + 字符串 组合隐式表达
phase = 0  # 还是 1? 还是 2? 还是 3?
evaluation_path = "use"  # 还是 "learn"?
```

没有显式的状态定义、状态转移表、或状态枚举。开发者必须通读 `continue_evaluation` 的全部 106 行 if/elif 才能理解"现在在哪个状态、下一步能去哪"。

#### 4. 没有任何测试

零测试文件。评估逻辑有大量分支（学/用 × 7个问题 × 每个问题的输入验证），每改一次都可能引入回归，但没有任何安全网。

---

## 三、屎山化风险评估

从当前代码结构看，有 **3 条明确的屎山化路径**：

### 路径 1：`core.py` 持续膨胀 🔴 高风险

```
现在: 588行, 3个评估路径
6个月后: 1500行, 8个评估路径, 3种报告模板, 2种对话模式
1年后: 没人敢改这个文件
```

**触发条件**：每次加新功能（新的评估分支、新的报告格式、新的对话模式）都在 core.py 里加 if/elif。

**预防**：拆分为独立模块 — `llm_client.py`、`evaluation/` (状态机 + 路径)、`report/` (模板)。

### 路径 2：`config.py` 变成垃圾场 🟠 中风险

```
现在: 240行, 8个场景, 7个问题
6个月后: 500行, 20个场景, 15个问题, 5种报告模板
```

**触发条件**：每次加内容都在 config.py 里追加字典。

**预防**：业务数据抽到 YAML/JSON 文件或独立的 data/ 目录。

### 路径 3：评估逻辑变成意大利面条 🟠 中风险

```
现在: continue_evaluation 106行, 2条路径
未来: 5条路径, 每条3-5步, 每步有验证+重试+分支
```

**触发条件**：新路径用同样的 if/elif 嵌套模式添加。

**预防**：用显式状态机模式重构。

---

## 四、具体代码问题

### 4.1 `continue_evaluation` — 106 行嵌套 if/elif

**文件**: `agent/core.py:223-329`

```
phase == 0
  └── is_use? → 展示场景列表
  └── !is_use? → 展示问题 0
evaluation_path == "use"
  └── phase == 1 → 匹配场景 + 展示问题
  └── phase == 2 → 匹配答案 + 展示问题
  └── phase == 3 → 匹配答案 + 生成报告
evaluation_path == "learn"
  └── q_idx = phase - 1 → 匹配答案 → 下一题 or 生成报告
```

每加一条路径，嵌套就多一层。这段代码已经接近人类可维护的临界点。

### 4.2 工具注册是手动的

**文件**: `agent/tools.py:230-234`

```python
TOOL_FUNCTIONS = {
    "search_web": search_web,
    "recommend_cloud_computer": recommend_cloud_computer,
    "generate_learning_path": generate_learning_path,
}
```

加一个新工具需要：写函数 → 加 TOOL_DEFINITIONS → 加 TOOL_FUNCTIONS → 注意 sync/async 区分。四处改动，容易遗漏。

### 4.3 `execute_tool` 里有特殊分支

**文件**: `agent/tools.py:243-244`

```python
if name == "search_web":
    return await func(**args)
return func(**args)  # ← 其他工具是同步的
```

靠函数名字符串判断是否 async。如果新工具也是 async，开发者必须记得加到这个 if 里。

### 4.4 报告生成是纯字符串拼接

**文件**: `agent/core.py:460-588`（128 行）

`generate_report` 用 f-string 拼接 Markdown，包含大量硬编码的业务逻辑（DIRECTION_MAP、LEVEL_MAP、LEVEL_ABILITY）。修改报告格式需要改 Python 代码，内容运营无法独立工作。

### 4.5 知识检索精度低

**文件**: `knowledge/retriever.py:86-89`

```python
if kw in tag.lower() or tag.lower() in kw:
    score += 1
```

"学" 匹配 "学习"、"学生"、"大学"。"AI" 匹配所有含 "AI" 的标签。知识库扩大后会返回大量不相关结果。

### 4.6 前端没有错误恢复

**文件**: `web/static/app.js`

SSE 流中断、网络错误、后端 500 — 都只是 `console.warn` + 一个 "出错了" 文本。没有重试机制、没有断线重连、没有会话恢复提示。

---

## 五、可维护性评分

| 维度 | 评分 | 说明 |
|------|------|------|
| **代码可读性** | ⭐⭐⭐⭐ | 命名清晰，中文注释到位，逻辑不绕 |
| **模块化** | ⭐⭐⭐ | 有分层，但 core.py 是单点故障 |
| **可扩展性** | ⭐⭐ | 加新评估路径/工具需要改多处，无插件机制 |
| **可测试性** | ⭐ | 零测试，全局状态多，难以 mock |
| **部署友好度** | ⭐⭐⭐⭐ | Docker 化完整，环境变量配置 |
| **文档** | ⭐⭐⭐ | README 和 AGENTS.md 有，但缺架构文档 |

**总体**：MVP 阶段够用，但**不具备可持续迭代的架构基础**。

---

## 六、重构建议（按优先级）

### P0 — 拆分 core.py（防止屎山化）

```
agent/
├── core.py           → 只保留 handle_message 路由
├── llm_client.py     → get_client, ask_llm, generate_stream
├── evaluation/
│   ├── __init__.py
│   ├── state.py      → 状态枚举 + 转移表
│   ├── paths.py      → learn_path, use_path (各自独立)
│   └── report.py     → 报告生成（可用 Jinja2 模板）
└── tools/
    ├── __init__.py   → 注册装饰器 + execute_tool
    ├── search.py
    ├── cloud.py
    └── learning.py
```

### P1 — 业务数据外部化

```
data/
├── evaluation/
│   ├── first_question.json
│   ├── learn_questions.json
│   └── use_scenarios.json
└── reports/
    └── template.md   (Jinja2 模板)
```

### P2 — 加测试

至少覆盖：

- 评估状态机的每条路径
- 工具执行的参数验证
- 报告生成的各种输入组合

### P3 — 工具注册用装饰器

```python
@register_tool(description="搜索网络")
async def search_web(query: str) -> str:
    ...

# 自动注册到 TOOL_DEFINITIONS 和 TOOL_FUNCTIONS
# 自动处理 sync/async 区分
```

---

## 七、结论

> **当前状态**：结构清晰的 MVP，代码质量高于平均水平。
>
> **屎山风险**：**中等偏高**。不是现在是屎山，而是**已经具备了变成屎山的结构条件** — 特别是 core.py 的膨胀路径和 config.py 的混合职责。
>
> **关键判断**：如果这个项目只是个人学习项目、不会再加功能，当前架构完全够用。如果要继续迭代（加新的评估路径、新的渠道、新的内容），**现在就该拆分 core.py**，否则每加一个功能的边际成本会越来越高。
