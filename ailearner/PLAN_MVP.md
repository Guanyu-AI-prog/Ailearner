# AILearner MVP 升级计划

目标：将 ailearner 从 Demo 升级为面试可展示的 MVP，重点解决三个问题：
1. 会话持久化（SQLite）
2. Docker 部署
3. README 补完

---

## 一、SQLite 会话持久化

### 现状
`main.py` 用内存 dict 存会话：`sessions: Dict[str, SessionState] = {}`
重启即丢失所有对话和评估状态。

### 改动方案

**新建 `db.py`**，负责所有数据库操作：

```python
# db.py 核心设计

# 表结构（2张表）
"""
sessions 表:
  - session_id TEXT PRIMARY KEY
  - evaluation_started INTEGER DEFAULT 0
  - evaluation_done INTEGER DEFAULT 0
  - evaluation_phase INTEGER DEFAULT 0
  - evaluation_report TEXT DEFAULT ''
  - created_at TIMESTAMP
  - updated_at TIMESTAMP

messages 表:
  - id INTEGER PRIMARY KEY AUTOINCREMENT
  - session_id TEXT
  - role TEXT          -- 'user' / 'assistant'
  - content TEXT
  - created_at TIMESTAMP
  - FOREIGN KEY (session_id) REFERENCES sessions(session_id)
"""

# 提供4个函数：
def init_db()                    # 建表，应用启动时调用一次
def get_session(session_id) -> dict   # 读会话+历史消息
def save_message(session_id, role, content)  # 存一条消息
def update_session(session_id, **kwargs)     # 更新评估状态
def delete_session(session_id)       # 重置会话时用
def close_db()                     # 应用关闭时调用
```

**修改 `agent/schemas.py`**：
- `SessionState` 不再作为内存对象，改为每次请求从DB加载
- `evaluation_answers` 改存JSON字符串到 `sessions` 表（新增 `evaluation_answers TEXT` 列）

**修改 `main.py`**：
- 删除 `sessions: Dict[str, SessionState] = {}` 全局变量
- `get_or_create_session()` 改为从DB读取，没有则创建
- `chat` 接口里，每轮对话结束后调用 `save_message()` 和 `update_session()`
- `reset_session` 改为调用 `delete_session()`
- lifespan 里加 `init_db()` 和 `close_db()`

**注意**：
- 评估答案 `evaluation_answers` 是个 dict，序列化成 JSON 字符串存 TEXT 列
- 不用 ORM，直接用 Python 标准库 `sqlite3`
- 数据库文件放在项目根目录：`ailearner.db`
- `.gitignore` 里加上 `*.db`

---

## 二、Docker 部署

### 新建 `Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装依赖（利用Docker缓存层）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 新建 `docker-compose.yml`

```yaml
version: '3.8'
services:
  ailearner:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./ailearner.db:/app/ailearner.db   # 持久化数据库
      - ./knowledge/data:/app/knowledge/data  # 知识库目录
    env_file:
      - .env
    restart: unless-stopped
```

### 新建 `.dockerignore`

```
.git
__pycache__
*.pyc
*.db
.env
output/
```

### 注意事项
- `.env` 文件不要打包进镜像，通过 `env_file` 或 `environment` 注入
- 数据库文件和知识库目录挂载为 volume，容器重启不丢数据
- requirements.txt 里确保有 `uvicorn`，如果没有要加上

---

## 三、README 补完

### 重写 `ailearner/README.md`，包含以下内容：

```markdown
# AI 学习引路人（AILearnerAgent）

一个帮助普通人判断"该不该学AI、学什么方向、怎么零成本入门"的智能 Agent。

## 功能

- **智能评估**：通过7个问题判断用户是否适合学AI、学到什么程度
- **知识库检索**：基于向量相似度匹配学习资源
- **工具调用**：网络搜索、云电脑推荐、学习路径生成
- **流式对话**：SSE 实时输出，体验流畅

## 技术栈

| 组件 | 技术选型 | 选型理由 |
|------|----------|----------|
| 后端框架 | FastAPI | 异步支持好，自带OpenAPI文档 |
| LLM对接 | OpenAI SDK（兼容API） | 硅基流动/DeepSeek等都兼容 |
| 向量检索 | NumPy余弦相似度 | 轻量，无需额外服务 |
| 会话存储 | SQLite | 单文件数据库，零运维 |
| 前端 | Jinja2 + 原生JS | 无框架依赖，部署简单 |

## 架构

```
用户 → 浏览器(FastAPI渲染) → main.py(FastAPI)
                                  ↓
                          agent/core.py (核心路由)
                          ↓              ↓
                    knowledge/        agent/tools.py
                    retriever.py      (搜索/推荐/路径)
                          ↓
                    config.py → LLM API (硅基流动)
```

## 快速开始

### 本地运行
1. 安装依赖：`pip install -r requirements.txt`
2. 配置环境变量：`cp .env.example .env`，填入 API Key
3. 启动：`python main.py`
4. 访问：http://localhost:8000/chat

### Docker 部署
1. 配置环境变量：`cp .env.example .env`
2. 启动：`docker-compose up -d`
3. 访问：http://localhost:8000/chat

## 项目结构

```
ailearner/
├── main.py              # FastAPI 入口
├── config.py            # 配置管理
├── db.py                # SQLite 持久化
├── agent/
│   ├── core.py          # 核心对话逻辑
│   ├── schemas.py       # 数据模型
│   ├── prompts.py       # Prompt 模板
│   └── tools.py         # 工具函数
├── knowledge/
│   ├── loader.py        # Markdown 解析
│   ├── retriever.py     # 向量检索
│   └── data/
│       └── resources.md # 知识库文件
├── web/
│   ├── templates/       # Jinja2 模板
│   └── static/          # CSS/JS
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## 评估流程

```
用户说"帮我评估"
  → 触发关键词匹配
    → 逐个提问（7题：目标/背景/时间/数学/编程/预算/方向）
      → 收集回答存入 SQLite
        → 生成评估报告（LLM + 规则混合）
          → 输出建议（学/不学 + 水平 + 方向 + 路径）
```

## 后续规划

- [ ] RAG 升级：接入 embedding 模型 + ChromaDB
- [ ] 评估智能化：LLM 动态追问替代固定题库
- [ ] 用户系统：登录注册 + 历史记录查看
- [ ] 管理后台：用户数据统计 + 知识库管理
```

---

## 执行顺序

1. **先做 SQLite**（改 db.py + 改 main.py + 改 schemas.py）
2. **再做 Docker**（Dockerfile + docker-compose + .dockerignore）
3. **最后写 README**（等前两步做完再写，确保描述准确）

每完成一步，本地测试一下再继续。
