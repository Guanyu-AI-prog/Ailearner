# 项目公约（每次任务前读取）

## 1. 一个文件只干一件事
- agent/ → 逻辑，knowledge/ → 数据，web/ → 前端
- core.py 不超过 500 行，超了就拆

## 2. 知识库内容和代码分离
- knowledge/data/ 只放 .md 文件，加内容不加代码
- tags.json 和代码逻辑分开

## 3. 每次只改一个东西
- 加功能不加重构，改哪只改哪，不顺手修别的

## 4. 改之前先读
- 改一个文件前，先通读全文，搞清全局状态再动手

## 5. 加功能先写 TODO 占位
- 不确定实现就写 `# TODO: 说明`，不直接堆 if-else

---

# 已完成的任务记录

## 2026-07-09: TF-IDF → 标签路由
- 改了 `knowledge/retriever.py`：去掉 TF-IDF（numpy、_tokenize、_build_vector、_vocab、_doc_vectors），改为加载 `tags.json`，按关键词匹配标签返回整篇文章
- 新建 `knowledge/tags.json`：8 篇文章的标签映射
- 未动 `main.py`、`agent/`、`web/`、`loader.py`、`core.py`
- 验证通过：每个查询正确匹配对应文章，"天气"等无关查询返回空

## 2026-07-09: L1 科普路径改为"使用 AI"导向
- 改了 `agent/core.py` 的 `steps["L1 科普"]`：从原来的"了解 AI/体验工具/培养思维"改为 4 步实践路径——用 Agent 型 AI → 申请 MiMo API Key → 准备环境（电脑/无影云电脑）→ 对接微信等日常平台
- 只改了 `steps` 字典的 L1 条目，未动其他逻辑

## 2026-07-09: MVP 升级——SQLite + Docker + README
- 新建 `db.py`：SQLite 会话持久化，2 张表（sessions/messages），6 个函数
- 改写 `main.py`：删除 `sessions.json` 文件持久化和内存 dict，全部走 `db.py`
- 新建 `Dockerfile` + `docker-compose.yml` + `.dockerignore`
- 重写 `README.md`：更新为标签路由、SQLite、Docker 等最新状态
- 从 `requirements.txt` 移除 `numpy`（已无引用）
- 更新 `.gitignore`：加 `*.db`

## 2026-07-09: CODE_REVIEW 修复（10 项）
- **#1** `main.py` 三元表达式加括号 `(report[:200] + "...")`
- **#2** `core.py:build_context` 改为展示标签（tags），去掉废弃的 type/level/direction
- **#3** `core.py:normal_chat` 流式/非流式工具调用均改为批量合成一条 assistant 消息
- **#4** 清理死代码：删除 `loader.py`、`schemas.py` 中 4 个未用类、`prompts.py` 中 2 个未用 prompt、`core.py` 中 `is_first_interaction`
- **#6** `db.py:update_session` 加列名白名单 `_ALLOWED_COLS`
- **#8** `app.js` 链接渲染加 `^https?://` 协议白名单防 XSS
- **#10** `.dockerignore` 加 `.env`

## 2026-07-10: 代码质量修复（10 项）
- **#1** `core.py:321-323` 修复级别判断 bug：`"L3","L4"` → `"L3 进阶","L4 专业"`，数学/编程零基础的降级兜底现在能正确生效
- **#3** `core.py:130` 修复 tool call ID：使用 LLM 返回的真实 ID（`tc["id"]`），不再伪造
- **#5** `app.js:133` 修复 XSS：`innerHTML` → `document.createElement` + `textContent`
- **#6** 输入长度限制 + 频率限制：`ChatRequest.message` 加 `max_length=2000`，`main.py` 加 per-session 速率限制（60s 内最多 20 次）
- **#7** `db.py` 重构连接管理：`_get_conn()` → `get_conn()` context manager，所有函数统一用 `with get_conn()`
- **#8** `main.py` `print()` → `logging`，配置 `basicConfig` 带时间戳和级别
- **#9** Docker 优化：`Dockerfile` 加非 root 用户 + healthcheck；`docker-compose.yml` 移除废弃的 `version: '3.8'`
- **#10** `db.py:close_db` 复用 `get_conn()` context manager，不再单独建连接
- **#11** 删除遗留的 `sessions.json`（SQLite 迁移后已无用）
- **#12** `agent/tools.py` `import re` 从函数体移到模块顶部

## 2026-07-13: 第二期代码审查修复（P1-P4）
- **P1** `agent/core.py:59` 流式工具调用 yield 增加 `"id": tc_data["id"]`，多工具并发时使用 LLM 真实 ID
- **P2** 新建 `routes/_common.py`，将 `_save_state` 提取为共享 `save_state`；`routes/chat.py` 和 `routes/evaluation.py` 统一导入，清理私有函数耦合和 stale import
- **P3** `agent/tools.py:223` 标题占位符 `"??"` → `"##"`
- **P4** `agent/core.py:460+316` 去掉 `generate_report` 多余 async/await
- 新建 `CODE_REVIEW_2.md`：第二期审查报告文档

# Git推送规则
- 远程仓库：git@github.com:Guanyu-AI-prog/Ailearner.git
- 每次改动后推送到GitHub
- 凭据：SSH key `~/.ssh/id_ed25519_github`，已在 `~/.ssh/config` 里绑定 `github.com`，不必再手动 `-i`
- 私钥设了 passphrase，钥匙串已记住。非交互环境若报 `Permission denied (publickey)`，先执行 `ssh-add --apple-use-keychain ~/.ssh/id_ed25519_github`
- **不要把 token、密钥、口令明文写进本文件**——本文件随仓库推送，写进来等于公开泄露


