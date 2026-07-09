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
