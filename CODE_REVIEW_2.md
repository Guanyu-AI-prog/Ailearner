# ailearner 代码审查报告（第二期）

> 审查日期：2026-07-13
> 审查范围：全项目文件（约 1,500 行有效代码）
> 基于第一期 CODE_REVIEW（2026-07-09）修复后的迭代审查

---

## 修复验证：上一期问题确认

| # | 问题 | 状态 | 验证方式 |
|---|------|------|----------|
| 1 | `main.py:108` 报告截断运算符优先级 | ✅ 已修复 | `main.py:75` 已加括号 `(report[:200] + "...")` |
| 2 | `build_context` 知识库 metadata 为空 | ✅ 已修复 | `core.py:84-88` 改用 `tags` 展示，去掉了废弃的 `type/level/direction` |
| 3 | 流式工具调用复用 `call_1` | ✅ 已修复 | `normal_chat` 改为一次合成一条 assistant 消息（但存在新问题，见 🔴#1） |
| 4 | 死代码 / 孤儿模块 | ✅ 已清理 | `loader.py` 未删但已无引用；`is_first_interaction`、未用 prompt/schema 已清理 |
| 5 | 搜索源 DuckDuckGo → Bing | ✅ 已更换 | `tools.py` 已换用 `cn.bing.com/search` |
| 6 | `db.py:update_session` 列名拼接 | ✅ 已修复 | 已加 `_ALLOWED_COLS` 白名单校验 |
| 7 | 默认模型可能存在性 | ⚠️ 待确认 | `DeepSeek-V4-Flash` / `DeepSeek-R1` 取决于运行时的 .env 配置 |
| 8 | XSS `javascript:` 协议 | ✅ 已修复 | `app.js` 链接渲染有 `^https?://` 白名单 |
| 9 | 信心指数硬编码 | ⚠️ 部分修复 | `core.py:526` 改为动态 `max(0.3, min(0.95, 0.85 - unknown_ratio * 0.55))` |
| 10 | `.env` 镜像泄露 | ✅ 已修复 | `.dockerignore` 已排除 `.env` |

---

## 🔴 中等问题

### 1. 流式工具调用 yield 丢弃了 `id` 字段

**文件**：`agent/core.py:57-59` + `141`
**影响**：多工具并发时，下游收到错误的 tool_call_id，不符合 OpenAI 格式规范。

`generate_stream`（第 57-59 行）收集了 LLM 返回的真实 `tc.id`，但 yield 时丢弃了 `"id"`：

```python
# core.py:57-59
if tool_calls_buffer:
    for tc_data in tool_calls_buffer.values():
        yield {"type": "tool_call", "name": tc_data["name"], "arguments": tc_data["arguments"]}
        #                    ^^ 缺少 "id" 字段 — tc_data["id"] 被丢弃
```

下游 `normal_chat`（第 141 行）因此永远拿不到真实 ID，fallback 到伪造 ID：

```python
tc_id = tc.get("id", "") or f"call_{tc['name']}"  # ← "id" 永远为空
```

当 LLM 一次返回多个工具调用时，所有 tool_call 的 `id` 都是伪造的 `call_search_web` / `call_recommend_cloud_computer`，而非 LLM 返回的真实 ID，可能导致：
- 下游消息格式不符合 OpenAI 规范
- 部分 LLM 服务端拒绝接受非匹配的 tool_call_id

**对比**：非流式路径（第 170 行）正确使用了 `tc.id`，说明修复只做了非流式部分。

**修复**（1 行改动）：

```python
# core.py:58 — 加上 "id"
yield {"type": "tool_call", "name": tc_data["name"], "arguments": tc_data["arguments"], "id": tc_data["id"]}
```

---

### 2. `routes/evaluation.py` 跨模块导入私有函数

**文件**：`routes/evaluation.py:10`
**影响**：模块封装被破坏，重构 `chat.py` 时可能无声破坏 `evaluation.py`。

```python
from routes.chat import _save_state  # ← 导入私有函数
```

Python 的下划线前缀约定表示"内部实现，请勿外部使用"。`routes/evaluation.py` 和 `routes/chat.py` 是两个平级路由子模块，这种跨模块引用私有函数意味着：

- 当 `chat.py` 重构 `_save_state`（例如签名变化、拆分为多个函数）时，`evaluation.py` 会无声出错
- 违反了模块封装原则，两个路由模块隐式耦合

**修复建议**：将 `_save_state` 提取到共享位置（如 `db.py` 或新建 `routes/_common.py`），两个路由模块各自导入公开的 API。

---

## 🟡 低风险问题 / 代码异味

### 3. `tools.py` 标题占位符 `"??"` 暴露到用户界面

**文件**：`agent/tools.py:223`

```python
path_text = f"?? {direction} 学习路径（目标：{target_level}）\n\n"
#             ^^ 应为 "##"
```

Markdown 标题应使用 `##`，当前输出为 `?? 文字相关 学习路径`，像是未完成的占位符。影响用户视觉体验。

**修复**：`??` → `##`

---

### 4. `generate_report` 标记为 `async` 但无 `await`

**文件**：`agent/core.py:460`

```python
async def generate_report(state: SessionState) -> str:
    # 全同步操作，无任何 await
    return report
```

整个函数体是纯同步计算（f-string 拼接、字典查询），无任何 IO 操作。标记为 `async` 会迷惑维护者，让人误以为此函数有异步行为。

**修复**：去掉 `async`，调用处也去掉 `await`。

---

### 5. `retriever.py` 函数名拼写错误 `knowledge` → `knowledge`

**文件**：`knowledge/retriever.py:67`

```python
def is_knowledge_ready() -> bool:
```

函数名拼写为 `knowledge`（漏了 `w`）。因 `main.py:32` 和 `test_personas.py` 使用相同拼写，运行无错，但任何搜索 `knowledge` 的人都会错过此函数。

注：文件整体位于 `knowledge/` 目录下，这一目录名拼写正确，只有此函数名拼写有误。

**修复**：重命名为 `is_knowledge_ready`，同步修改所有调用处。

---

### 6. `config.py` 混合基础设施配置和业务内容数据

**文件**：`config.py:1-256`
**影响**：内容运营无法独立工作，每次改评估问题或场景都需要改 Python 代码。

| 类别 | 行数占比 | 示例 |
|------|----------|------|
| 基础设施配置 | ~15 行 (6%) | API Key、模型名、端口 |
| 业务内容数据 | ~210 行 (82%) | 评估问卷 (7 题)、场景模板 (8 个)、Prompt 模板 |
| 其他 | ~30 行 | 类定义、config 实例化 |

**进展**：第一期 ARCHITECTURE_REVIEW 已指出此问题，尚未开始重构。

**历史建议**：将业务数据抽到 `data/` 目录下的 JSON/YAML 文件，或独立到 `knowledge/` 目录下。

---

### 7. 速率限制清理间隔过长

**文件**：`routes/chat.py:27`

```python
if now - _last_cleanup > 300:  # 每 300 秒（5 分钟）才清理一次
```

在此期间，过期 session 的速率限制条目会持续占用内存。对低流量（<100 活跃 session）影响可忽略，但如果扩展到大量用户，`_rate_limits` OrderedDict 可能积累大量已过期条目。

**建议**：缩短到 60 秒，或在每次请求时惰性清理当前 session 的过期条目（已对当前 session 做惰性清理，但其他 session 的过期条目要到 5 分钟后才清理）。

---

### 8. 测试脚本硬编码地址和路径

**文件**：`test_personas.py:10-11`

```python
API_BASE = "http://127.0.0.1:8000"
output_path = "/home/admin/ailearner/test_results.json"
```

测试运行前必须确保服务已在 8000 端口运行。端口和输出路径无法通过环境变量或命令行参数配置。

**建议**：改为 `API_BASE = os.getenv("TEST_API_BASE", "http://127.0.0.1:8000")`，路径同理。

---

### 9. 后端缺少 CORS 中间件

当前后端未配置 CORS 中间件。如果将来需要从不同域名的前端调用 API（如嵌入第三方网站、浏览器扩展等），浏览器会因同源策略阻止跨域请求。

当前前后端同域名部署（FastAPI 渲染模板），暂不影响。但如需对外开放 API，需要添加。

---

## ✅ 做得好的地方

| 方面 | 说明 |
|------|------|
| **XSS 防护** | `app.js` 使用 DOMPurify + `textContent` 渲染用户内容，`innerHTML` 已替换 |
| **SQL 注入防护** | `db.py` 的 `_ALLOWED_COLS` 白名单校验，列名不可注入 |
| **Docker 安全** | 非 root 用户 + healthcheck + `.dockerignore` 排除 `.env` |
| **模块分层** | `routes/` 子模块拆分合理，`main.py` 仅 92 行启动代码 |
| **日志** | 已用 `logging.basicConfig` 替代 `print`，带时间戳和级别 |
| **输入验证** | `ChatRequest.message` 有 `max_length=2000`，每 session 60s 内最多 20 次请求 |
| **异步全链路** | FastAPI + aiosqlite + AsyncOpenAI，不会阻塞事件循环 |
| **用户提示词** | `prompts.py` 的 SYSTEM_PROMPT 质量高，诚实、务实、场景化 |

---

## 可维护性评分（对比第一期）

| 维度 | 第一期 | 本期 | 变化说明 |
|------|--------|------|----------|
| **代码可读性** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 命名清晰，注释到位 |
| **模块化** | ⭐⭐⭐ | ⭐⭐⭐ | 本期未做重构，`core.py` 仍然膨胀 |
| **可扩展性** | ⭐⭐ | ⭐⭐ | 同上，未改善 |
| **可测试性** | ⭐ | ⭐⭐ | 新增 `test_personas.py`，覆盖 3 条人设路径 |
| **部署友好度** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | Docker 化完整 |
| **文档** | ⭐⭐⭐ | ⭐⭐⭐ | 无变化 |

---

## 修复优先级建议

| 优先级 | 问题 | 影响 | 工作量 |
|--------|------|------|--------|
| **P1** | 流式工具调用 ID 丢失 | 多工具并发时格式错误 | 1 行 |
| **P2** | `_save_state` 跨模块耦合 | 维护隐患 | 中等（提取共享函数） |
| **P3** | `"??"` 占位符暴露 | 用户体验 | 1 行 |
| **P4** | `generate_report` 多余 `async` | 代码异味 | 1 行 |
| **P5** | 函数名拼写 `knowledge` | 可发现性 | 1 行 + 查找调用处 |

---

*本报告基于逐文件通读 + 交叉引用检查 + AST 语法验证生成。*