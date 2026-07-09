# ailearner 代码审查报告

审查日期：2026-07-09
审查范围：`main.py` / `config.py` / `db.py` / `agent/*` / `knowledge/*` / `web/static/app.js`
整体评价：结构清晰、模块划分符合 AGENTS.md 约定，但存在 3 个严重 Bug 和若干中低危问题。

---

## 🔴 严重 Bug

### 1. `main.py:108` 报告截断失效（运算符优先级）
```python
report[:200] + "..." if len(report) > 200 else report
```
由于 `+` 优先级高于三元表达式，实际解析为 `report[:200] + ("..." if ... else report)`。
当 `len>200` 时三元取 `else` 分支返回完整 `report`，结果变成 `report[:200] + report`（整段没截断）。

修复：
```python
(report[:200] + "...") if len(report) > 200 else report
```

### 2. `core.py:84-88` 知识库 metadata 字段永远为空
`build_context` 读取 `metadata.get('type')` / `metadata.get('level')` / `metadata.get('direction')`，
但 `retriever.py:99-102` 返回的 metadata 只有 `{"title", "tags"}`。下游的「水平/方向/类型」行永远是空的。

修复方向：在 `retriever.py` 返回 `loader.py` 已解析的 `type/level/direction`（见 #4），或在 `build_context` 去掉这些字段。

### 3. `core.py` 流式工具调用复用 `call_1`，多工具调用产生非法对话格式
`normal_chat` 每收到一个 `tool_call` chunk，就用固定 `id="call_1"` 追加一条 assistant 消息和一条 `tool` 消息（`core.py:127-130`）。
若模型一次请求发出 2 个工具调用：会出现两条 `id="call_1"` 的 tool_calls 和两条 `tool_call_id="call_1"` 的消息。
OpenAI 要求 tool_call 必须在同一条 assistant 消息里、且 `id` 唯一。

修复方向：收集本轮所有 tool_call 后，一次性合成一条包含全部 `tool_calls` 的 assistant 消息，
并以真实 `tc.index` 作为 id（消费侧需区分 `tc.index`）。

---

## 🟡 中等问题

### 4. 大量死代码 / 孤儿模块
- `knowledge/loader.py` 整个文件已不被 `retriever.py` 使用（TF-IDF→标签路由改造后废弃），建议删除或重新接入（顺便解决 #2）。
- `prompts.py` 的 `EVALUATION_SYSTEM_PROMPT`、`REPORT_PROMPT` 从未被调用（`generate_report` 为纯 Python 实现）。
- `schemas.py` 的 `EvaluationResult`、`ChatResponse`、`ToolCall`、`LLMResponse` 从未使用。
- `core.py` 的 `is_first_interaction` 从未使用。

### 5. `tools.py:80` `search_web` 用 DuckDuckGo 即时答案 API
`api.duckduckgo.com/?q=...&format=json` 已被弃用/不稳定，几乎总是返回空，触发「未找到」兜底。
建议换用可靠搜索源（SerpAPI / Brave Search / siliconflow 检索）。

### 6. `db.py:97-103` `update_session` 用 f-string 拼列名
列名来自调用方 kwargs，目前均为受控常量，无外部注入风险，但属脆弱写法。
建议加白名单校验列名：`if key not in ALLOWED_COLUMNS: raise`。

### 7. `config.py:13` 默认模型可能不存在
`deepseek-ai/DeepSeek-V4-Flash` 需确认在 siliconflow 上确实存在，否则所有 `/api/chat` 直接 500
（错误信息会回传给前端，见 `main.py:78`）。

---

## 🟢 低风险 / 建议

### 8. XSS 风险（前端）`app.js:150`
链接渲染未过滤 `javascript:` 协议。虽内容来自模型，但建议对 `href` 做协议白名单校验（`^https?://`）。

### 9. `generate_report` 信心指数硬编码 `0.85`（`core.py:368`）
可考虑按回答完整度动态计算，否则与「诚实」定位略有出入。

### 10. `.env` 明文 API Key 镜像泄露风险
`.env` 已被 `.gitignore` 正确忽略 ✅，但当前 `.dockerignore` 未列出 `.env`，
打 Docker 镜像时存在密钥泄露风险，应在 `.dockerignore` 中排除 `.env`。

---

## 修复优先级建议
1. #1（一行修复，立即生效）
2. #2 + #4（重新接入 loader 解析的 metadata，删除死代码）
3. #3（流式多工具调用的正确对话格式）
4. #10（.dockerignore 加 .env，安全）
5. 其余按需要排期
